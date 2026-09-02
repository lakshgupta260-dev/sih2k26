"""Extraction, matching and review contracts."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.constants import MatchStatus
from app.schemas.common import ORMModel


class ExtractedActivityRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    progress_report_id: uuid.UUID
    source_ref: str
    raw_text: str
    event_type: str
    activity_code: str | None
    discipline: str | None
    event_date: date | None
    percent_complete: float | None
    quantity: float | None
    uom: str | None
    chainage_from_m: float | None
    chainage_to_m: float | None
    joint_from: int | None
    joint_to: int | None
    extraction_confidence: float
    extractor: str
    created_at: datetime


class MatchCandidateRead(BaseModel):
    """One alternative the matcher considered, kept for reviewer context."""

    activity_id: uuid.UUID
    activity_code: str
    activity_name: str
    wbs_path: str
    level: int
    score: float
    method: str
    signals: dict[str, float] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)


class ActivityMatchRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    extracted_activity_id: uuid.UUID
    activity_id: uuid.UUID | None
    status: str
    auto_status: str
    method: str
    score: float
    reason: str | None
    signals: dict[str, Any]
    candidates: list[dict[str, Any]]
    embedding_provider: str | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


class ActivityMatchDetail(ActivityMatchRead):
    """A match plus the field text that produced it."""

    extracted: ExtractedActivityRead


class MatchRunRequest(BaseModel):
    """Run extraction and matching over one report, or the whole project."""

    progress_report_id: uuid.UUID | None = Field(
        default=None,
        description="Limit to one report. Omit to process every unprocessed report.",
    )
    schedule_id: uuid.UUID | None = Field(
        default=None,
        description="Schedule to match against. Defaults to the project's latest.",
    )
    auto_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    review_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    reprocess: bool = Field(
        default=False,
        description="Re-extract reports that already have extracted items.",
    )

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "MatchRunRequest":
        if (
            self.auto_threshold is not None
            and self.review_threshold is not None
            and self.review_threshold > self.auto_threshold
        ):
            raise ValueError("review_threshold cannot exceed auto_threshold.")
        return self


class MatchRunSummary(BaseModel):
    """What a matching run did. Deliberately explicit about extractor used."""

    reports_processed: int
    items_extracted: int
    matches_created: int
    auto_matched: int
    needs_review: int
    unmatched: int
    schedule_id: uuid.UUID | None
    extractors_used: list[str]
    embedding_provider: str
    llm_available: bool
    auto_threshold: float
    review_threshold: float


class MatchReviewDecision(BaseModel):
    """A human's verdict on a proposed link."""

    decision: str = Field(description="confirm | reject | reassign")
    activity_id: uuid.UUID | None = Field(
        default=None,
        description="Required for 'reassign'; the activity the line really means.",
    )
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _decision_valid(self) -> "MatchReviewDecision":
        allowed = {"confirm", "reject", "reassign"}
        if self.decision not in allowed:
            raise ValueError(f"decision must be one of {sorted(allowed)}")
        if self.decision == "reassign" and self.activity_id is None:
            raise ValueError("activity_id is required when reassigning a match.")
        if self.decision != "reassign" and self.activity_id is not None:
            raise ValueError("activity_id is only accepted when reassigning.")
        return self


class MatchStatsRead(BaseModel):
    """Queue and accuracy counters for the dashboard."""

    total: int
    auto_matched: int
    needs_review: int
    unmatched: int
    manually_confirmed: int
    manually_rejected: int
    # Of the machine's automatic links that a human has since ruled on, how
    # many were upheld. Empty until reviews exist.
    auto_precision: float | None = None
    reviewed_count: int = 0


class AuditEntryRead(BaseModel):
    """One line of a match's review history."""

    action: str
    actor_user_id: uuid.UUID | None
    created_at: datetime
    details: dict[str, Any]
