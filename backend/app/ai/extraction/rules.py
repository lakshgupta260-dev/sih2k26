"""Deterministic rule-based extractor.

This is real, working extraction -- not a placeholder. It classifies each line
by event type and pulls out activity code, chainage, joint band, percentage,
quantity and date using the vocabulary that actually appears in Indian
infrastructure daily progress reports.

It is the default because it is fast, free, reproducible and auditable. An LLM
extractor (``app/ai/extraction/llm.py``) can be layered on top when a key is
configured; the two are combined by the service, which records which extractor
produced each item.

The hardest judgement it makes is **future intent**. A line like "L&B to be
taken up tomorrow" reads exactly like progress but must never be booked as an
actual. Those are classified ``PLANNED_NOT_ACTUAL`` and carried through so the
pipeline can refuse them explicitly rather than dropping them silently.
"""
from __future__ import annotations

import re

from app.ai.extraction.base import (
    ActivityExtractor,
    normalise,
    parse_activity_code,
    parse_chainage,
    parse_date,
    parse_joints,
    parse_percent,
    parse_quantity,
    residual_text,
    split_lines,
)
from app.ai.schemas import EventType, ExtractedItem
from app.core.constants import Discipline

# ---------------------------------------------------------------- vocabulary
# Ordered longest-first where prefixes overlap, so "not started" is not
# matched as "started".
FUTURE_CUES = (
    "to be taken up", "to be continued", "to be completed", "to be started",
    "will be taken up", "will be started", "will continue", "will be completed",
    "planned for", "plan for", "scheduled for", "scheduled to", "is scheduled",
    "proposed to", "expected to", "shall be", "to commence", "to start",
    "tomorrow", "next week", "next month", "upcoming",
)
NEGATION_CUES = (
    "not started", "no progress", "nil progress", "not taken up",
    "could not", "not carried out", "suspended", "no work", "yet to",
    "not completed", "not achieved", "awaited", "pending",
)
FINISH_CUES = (
    "100% complete", "100 % complete", "fully completed", "completed and offered",
    "completed", "complete", "finished", "closed", "done", "achieved fully",
)
START_CUES = (
    "mobilised and started", "commenced", "started", "start taken",
    "taken up", "initiated", "began", "begun", "work started",
)
PROGRESS_CUES = (
    "in progress", "under progress", "ongoing", "continuing", "continued",
    "progressing", "wip", "work in progress", "executed today", "achieved",
)

# Words that mean the line is site administration, not an activity event.
NON_ACTIVITY_CUES = (
    "toolbox talk", "safety induction", "safety training", "hse meeting",
    "progress review meeting", "client walkdown", "gate pass", "diesel",
    "manpower mobilisation", "first-aid", "first aid", "medical",
    "calibration sent", "breakdown maintenance", "labour unrest",
    "tree cutting", "permission awaited", "consumables received",
    "material received", "mrir", "dust suppression", "night shift",
    "review meeting", "committee meeting", "induction",
)

DISCIPLINE_CUES: dict[str, Discipline] = {
    "civil": Discipline.CIVIL, "concret": Discipline.CIVIL, "shutter": Discipline.CIVIL,
    "foundation": Discipline.CIVIL, "excavat": Discipline.CIVIL, "backfill": Discipline.CIVIL,
    "pcc": Discipline.CIVIL, "rcc": Discipline.CIVIL, "blockwork": Discipline.CIVIL,
    "piping": Discipline.PIPING, "spool": Discipline.PIPING, "pipe support": Discipline.PIPING,
    "electrical": Discipline.ELECTRICAL, "cable": Discipline.ELECTRICAL,
    "mcc": Discipline.ELECTRICAL, "earthing": Discipline.ELECTRICAL,
    "glanding": Discipline.ELECTRICAL, "lighting": Discipline.ELECTRICAL,
    "instrument": Discipline.INSTRUMENTATION, "loop check": Discipline.INSTRUMENTATION,
    "impulse tubing": Discipline.INSTRUMENTATION, "calibrat": Discipline.INSTRUMENTATION,
    "mechanical": Discipline.MECHANICAL, "alignment": Discipline.MECHANICAL,
    "coupling": Discipline.MECHANICAL, "erection of pump": Discipline.MECHANICAL,
    "structural": Discipline.STRUCTURAL, "str steel": Discipline.STRUCTURAL,
    "structural steel": Discipline.STRUCTURAL, "pipe rack": Discipline.STRUCTURAL,
    "grouting": Discipline.STRUCTURAL,
    "weld": Discipline.WELDING_NDT, "radiograph": Discipline.WELDING_NDT,
    "ndt": Discipline.WELDING_NDT, " rt ": Discipline.WELDING_NDT,
    "root pass": Discipline.WELDING_NDT, "fill and cap": Discipline.WELDING_NDT,
    "survey": Discipline.SURVEY, "staking": Discipline.SURVEY, "rou": Discipline.SURVEY,
    "coating": Discipline.COATING, "jeeping": Discipline.COATING,
    "holiday detection": Discipline.COATING, "fjc": Discipline.COATING,
    "hydrotest": Discipline.TESTING_PRECOMMISSIONING,
    "hydrostatic": Discipline.TESTING_PRECOMMISSIONING,
    "pigging": Discipline.TESTING_PRECOMMISSIONING,
    "dewatering": Discipline.TESTING_PRECOMMISSIONING,
    "trial run": Discipline.TESTING_PRECOMMISSIONING,
}

# A "Plan for tomorrow" style section heading switches every following line to
# future intent until the next heading.
_FUTURE_SECTION = re.compile(
    r"^(?:[A-Z]\.\s*)?(planned?\s+for\s+tomorrow|plan\s+for\s+next|"
    r"tomorrow'?s?\s+plan|forward\s+plan)\b",
    re.IGNORECASE,
)
_SECTION_HEADING = re.compile(
    r"^(?:[A-Z]\.\s*)?(work\s+executed|work\s+done|progress|constraints?|"
    r"issues?|remarks?|entries|manpower|equipment)\b",
    re.IGNORECASE,
)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> str | None:
    for needle in needles:
        if needle in haystack:
            return needle
    return None


def detect_discipline(text: str) -> Discipline | None:
    padded = f" {text} "
    for cue, discipline in DISCIPLINE_CUES.items():
        if cue in padded:
            return discipline
    return None


def classify_event(text: str, *, in_future_section: bool = False) -> tuple[EventType, float, str]:
    """Classify a line. Returns (event type, confidence, reason).

    Order matters: future intent and negation are checked before the completion
    and start cues they would otherwise trigger.
    """
    low = normalise(text)

    cue = _contains_any(low, NON_ACTIVITY_CUES)
    if cue:
        return EventType.NONE, 0.85, f"site-administration cue '{cue}'"

    if in_future_section:
        return EventType.PLANNED_NOT_ACTUAL, 0.9, "line sits under a forward-plan heading"

    cue = _contains_any(low, FUTURE_CUES)
    if cue:
        return EventType.PLANNED_NOT_ACTUAL, 0.85, f"future-intent cue '{cue}'"

    cue = _contains_any(low, NEGATION_CUES)
    if cue:
        return EventType.NONE, 0.8, f"negation cue '{cue}'"

    cue = _contains_any(low, FINISH_CUES)
    if cue:
        return EventType.ACTUAL_FINISH, 0.8, f"completion cue '{cue}'"

    cue = _contains_any(low, START_CUES)
    if cue:
        return EventType.ACTUAL_START, 0.75, f"start cue '{cue}'"

    cue = _contains_any(low, PROGRESS_CUES)
    if cue:
        return EventType.PROGRESS_UPDATE, 0.7, f"progress cue '{cue}'"

    if parse_percent(low) is not None:
        return EventType.PROGRESS_UPDATE, 0.5, "percentage present, no explicit verb"

    return EventType.NONE, 0.3, "no event vocabulary found"


class RuleBasedExtractor:
    """Deterministic extractor. The default, and always available."""

    name = "rule_based"

    def extract(self, raw_text: str, *, source: str = "document") -> list[ExtractedItem]:
        items: list[ExtractedItem] = []
        in_future_section = False

        for index, line in split_lines(raw_text):
            if _FUTURE_SECTION.match(line):
                in_future_section = True
                continue
            if _SECTION_HEADING.match(line):
                in_future_section = False
                continue

            event_type, confidence, reason = classify_event(
                line, in_future_section=in_future_section
            )
            # Quantity is read from text with dates and location spans
            # blanked, so a chainage figure is never mistaken for a quantity.
            quantity = parse_quantity(residual_text(line))
            discipline = detect_discipline(normalise(line))

            item = ExtractedItem(
                raw_text=line,
                source_ref=f"{source}:line:{index}",
                event_type=event_type,
                activity_code=parse_activity_code(line),
                description=line,
                discipline=discipline.value if discipline else None,
                event_date=parse_date(line),
                percent_complete=parse_percent(line),
                quantity=quantity[0] if quantity else None,
                uom=quantity[1] if quantity else None,
                chainage=parse_chainage(line),
                joints=parse_joints(line),
                extraction_confidence=confidence,
                extractor=self.name,
                notes={"classification_reason": reason},
            )

            # An explicit code or a parsed location is strong evidence that the
            # line really is about a scheduled activity.
            if item.activity_code:
                item.extraction_confidence = min(1.0, item.extraction_confidence + 0.1)
            if item.chainage or item.joints:
                item.extraction_confidence = min(1.0, item.extraction_confidence + 0.05)

            items.append(item)
        return items


def get_rule_based_extractor() -> ActivityExtractor:
    return RuleBasedExtractor()
