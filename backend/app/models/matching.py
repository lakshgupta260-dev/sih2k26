"""Extracted field items and their links to plan activities."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import MatchMethod, MatchStatus
from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One candidate activity event pulled out of a progress report.

    Stored even when it turns out not to be an activity event at all
    (``event_type = NONE``) and even when nothing matches, because "what did
    this report say and what did we do with it" is the audit question that
    matters. Discarding unmatched lines would make the pipeline unauditable.
    """

    __tablename__ = "extracted_activities"
    __table_args__ = (
        Index("ix_extracted_activities_report_event", "progress_report_id", "event_type"),
        CheckConstraint(
            "percent_complete IS NULL OR (percent_complete >= 0 AND percent_complete <= 100)",
            name="pct_range",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    progress_report_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("progress_reports.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    source_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    activity_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_complete: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Locations are stored as plain numbers rather than a range type so they can
    # be indexed and compared with ordinary SQL in later phases.
    chainage_from_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    chainage_to_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    joint_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    joint_to: Mapped[int | None] = mapped_column(Integer, nullable=True)

    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    extractor: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    notes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    matches: Mapped[list["ActivityMatch"]] = relationship(
        back_populates="extracted_activity", cascade="all, delete-orphan"
    )


class ActivityMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A proposed or confirmed link from an extracted item to a plan activity.

    ``activity_id`` is nullable: an unmatched line still gets a match row, so
    the queue of things needing attention is a single query and the reason is
    recorded rather than inferred.

    ``signals`` and ``candidates`` exist so a reviewer can see *why* a link was
    proposed and what the alternatives were. Without that, human review is
    guesswork and the confidence score is unfalsifiable.
    """

    __tablename__ = "activity_matches"
    __table_args__ = (
        Index("ix_activity_matches_project_status", "project_id", "status"),
        CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        CheckConstraint(
            "status <> 'AUTO_MATCHED' OR activity_id IS NOT NULL",
            name="matched_requires_activity",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    extracted_activity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("extracted_activities.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MatchStatus.UNMATCHED, index=True
    )
    # The machine's original verdict, preserved even after a human overrides it,
    # so the matcher's accuracy can be measured against review decisions later.
    auto_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MatchStatus.UNMATCHED
    )
    method: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MatchMethod.HYBRID
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    extracted_activity: Mapped["ExtractedActivity"] = relationship(back_populates="matches")

    @property
    def needs_review(self) -> bool:
        return self.status == MatchStatus.NEEDS_REVIEW

    @property
    def is_confirmed(self) -> bool:
        return self.status in (MatchStatus.AUTO_MATCHED, MatchStatus.MANUALLY_CONFIRMED)
