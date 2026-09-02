"""Progress tracking models."""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
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


class ActualProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Historical record of progress for a specific activity on a specific date."""
    __tablename__ = "actual_progress"
    __table_args__ = (
        UniqueConstraint("activity_id", "reporting_date", name="uq_progress_activity_date"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # The absolute total quantity completed up to this reporting date
    actual_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Track the actual start and finish dates if they happened
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    status: Mapped[ActivityStatus] = mapped_column(
        String(32), nullable=False, default=ActivityStatus.NOT_STARTED
    )
    
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    activity: Mapped["Activity"] = relationship()
    reported_by: Mapped["User"] = relationship()
