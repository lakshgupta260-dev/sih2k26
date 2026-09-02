"""Extraction and matching value objects.

Deliberately free of SQLAlchemy and Pydantic: these are plain dataclasses so
the extraction and matching layers can be unit-tested without a database, and
so a provider can be swapped without any ORM coupling. The service layer is the
only place that translates between these and the models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """What a field line asserts about an activity."""

    ACTUAL_START = "ACTUAL_START"
    ACTUAL_FINISH = "ACTUAL_FINISH"
    PROGRESS_UPDATE = "PROGRESS_UPDATE"
    # Reads like progress but is not an actual event -- "to be taken up
    # tomorrow". Booking these is the most common way to corrupt a schedule.
    PLANNED_NOT_ACTUAL = "PLANNED_NOT_ACTUAL"
    NONE = "NONE"


@dataclass(frozen=True)
class ChainageRange:
    """A linear location, normalised to metres."""

    from_m: float
    to_m: float

    def overlap_ratio(self, other: "ChainageRange") -> float:
        """Intersection over union, 0.0 when disjoint."""
        lo = max(min(self.from_m, self.to_m), min(other.from_m, other.to_m))
        hi = min(max(self.from_m, self.to_m), max(other.from_m, other.to_m))
        inter = max(0.0, hi - lo)
        union_lo = min(min(self.from_m, self.to_m), min(other.from_m, other.to_m))
        union_hi = max(max(self.from_m, self.to_m), max(other.from_m, other.to_m))
        union = max(union_hi - union_lo, 1e-9)
        return inter / union


@dataclass(frozen=True)
class JointRange:
    """A girth-weld joint band."""

    from_no: int
    to_no: int

    def overlap_ratio(self, other: "JointRange") -> float:
        lo = max(min(self.from_no, self.to_no), min(other.from_no, other.to_no))
        hi = min(max(self.from_no, self.to_no), max(other.from_no, other.to_no))
        inter = max(0, hi - lo)
        union_lo = min(min(self.from_no, self.to_no), min(other.from_no, other.to_no))
        union_hi = max(max(self.from_no, self.to_no), max(other.from_no, other.to_no))
        union = max(union_hi - union_lo, 1)
        return inter / union


@dataclass
class ExtractedItem:
    """One candidate activity event pulled out of a field document.

    ``source_ref`` identifies where it came from (a line index, a sheet row, a
    page) so a reviewer can always trace a link back to the original text.
    """

    raw_text: str
    source_ref: str
    event_type: EventType = EventType.NONE
    activity_code: str | None = None
    description: str | None = None
    discipline: str | None = None
    event_date: date | None = None
    percent_complete: float | None = None
    quantity: float | None = None
    uom: str | None = None
    chainage: ChainageRange | None = None
    joints: JointRange | None = None
    # How confident the *extractor* is that this line is an activity event at
    # all. Distinct from match confidence, which is about which activity.
    extraction_confidence: float = 0.0
    extractor: str = "unknown"
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actual_event(self) -> bool:
        return self.event_type in (
            EventType.ACTUAL_START,
            EventType.ACTUAL_FINISH,
            EventType.PROGRESS_UPDATE,
        )


@dataclass(frozen=True)
class ActivityRef:
    """The plan-side activity a candidate may refer to.

    A flat projection of the ORM row, so the matcher never touches SQLAlchemy.
    """

    id: str
    activity_code: str
    name: str
    wbs_path: str
    level: int
    discipline: str | None = None
    chainage: ChainageRange | None = None
    joints: JointRange | None = None


@dataclass
class MatchSignals:
    """Per-signal scores, each in 0..1, with ``None`` meaning not applicable.

    Kept as a structured record rather than a single number because the review
    UI has to explain *why* a link was proposed, and because a signal that is
    absent must not be scored as zero.
    """

    exact_code: float | None = None
    keyword: float | None = None
    fuzzy: float | None = None
    embedding: float | None = None
    discipline: float | None = None
    location: float | None = None
    hierarchy: float | None = None

    def as_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class MatchCandidate:
    """A scored (extracted item, activity) pair."""

    activity: ActivityRef
    score: float
    signals: MatchSignals
    method: str
    explanation: list[str] = field(default_factory=list)


@dataclass
class MatchOutcome:
    """The matcher's verdict for one extracted item."""

    item: ExtractedItem
    candidates: list[MatchCandidate]
    status: str
    best: MatchCandidate | None = None
    reason: str = ""
