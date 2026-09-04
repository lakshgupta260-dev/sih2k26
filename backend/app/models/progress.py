"""Progress tracking models."""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ActivityStatus
from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.schedule import Activity
    from app.models.user import User
    from app.models.document import ProgressReport


class ActualProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Historical record of progress for a specific activity on a specific date."""
    __tablename__ = "actual_progress"
    __table_args__ = (
        UniqueConstraint("activity_id", "reporting_date", name="uq_progress_activity_date"),
        CheckConstraint("actual_quantity IS NULL OR actual_quantity >= 0", name="ck_progress_quantity_positive"),
        CheckConstraint("percent_complete IS NULL OR (percent_complete >= 0 AND percent_complete <= 100)", name="ck_progress_percent_range"),
        CheckConstraint(
            "actual_start IS NULL OR actual_finish IS NULL OR actual_start <= actual_finish",
            name="ck_progress_dates"
        ),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # The absolute total quantity completed up to this reporting date
    actual_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_complete: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Track the actual start and finish dates if they happened
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    status: Mapped[ActivityStatus] = mapped_column(
        String(32), nullable=False, default=ActivityStatus.NOT_STARTED
    )
    
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    
    source_report_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("progress_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )

    activity: Mapped["Activity"] = relationship()
    reported_by: Mapped["User"] = relationship()
    source_report: Mapped["ProgressReport"] = relationship()
