"""Schedule, Activity, and Dependency models."""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import JobStatus, Discipline, DependencyType
from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Schedule(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A project schedule containing a hierarchy of activities."""
    __tablename__ = "schedules"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    status: Mapped[JobStatus] = mapped_column(
        String(32), nullable=False, default=JobStatus.COMPLETED
    )

    project: Mapped["Project"] = relationship()
    uploaded_by: Mapped["User"] = relationship()
    activities: Mapped[list["Activity"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class Activity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An individual task/activity within a schedule."""
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("schedule_id", "activity_code", name="uq_activity_code_per_schedule"),
        CheckConstraint("level >= 1 AND level <= 6", name="ck_activities_level_range"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    activity_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    wbs_path: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    
    level: Mapped[int] = mapped_column(Integer, nullable=False) # e.g., 1-6
    discipline: Mapped[Discipline | None] = mapped_column(String(50), nullable=True)
    
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    budgeted_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=True, index=True
    )

    schedule: Mapped["Schedule"] = relationship(back_populates="activities")
    parent: Mapped["Activity | None"] = relationship(remote_side="Activity.id", back_populates="children")
    children: Mapped[list["Activity"]] = relationship(back_populates="parent")

    # Dependencies where this activity is the predecessor
    successors: Mapped[list["ActivityDependency"]] = relationship(
        foreign_keys="ActivityDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan"
    )
    # Dependencies where this activity is the successor
    predecessors: Mapped[list["ActivityDependency"]] = relationship(
        foreign_keys="ActivityDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan"
    )


class ActivityDependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Represents a relationship between two activities (e.g. Finish-to-Start)."""
    __tablename__ = "activity_dependencies"
    __table_args__ = (
        CheckConstraint("predecessor_id != successor_id", name="ck_activity_dependencies_no_self"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    dependency_type: Mapped[DependencyType] = mapped_column(String(20), nullable=False, default=DependencyType.FINISH_TO_START)
    lag: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    predecessor: Mapped["Activity"] = relationship(
        foreign_keys=[predecessor_id], back_populates="successors"
    )
    successor: Mapped["Activity"] = relationship(
        foreign_keys=[successor_id], back_populates="predecessors"
    )
