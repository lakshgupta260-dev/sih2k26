"""Progress request and response shapes."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import ActivityStatus


class ActualProgressCreate(BaseModel):
    reporting_date: date
    actual_quantity: float | None = Field(
        None, ge=0.0,
        description="Cumulative quantity completed as at the reporting date.",
    )
    percent_complete: float | None = Field(None, ge=0.0, le=100.0)
    actual_start: date | None = None
    actual_finish: date | None = None
    status: ActivityStatus = ActivityStatus.NOT_STARTED
    notes: str | None = None
    source_report_id: uuid.UUID | None = Field(
        None, description="Progress report this figure came from, if any."
    )

    @model_validator(mode="after")
    def check_dates(self) -> ActualProgressCreate:
        if self.actual_start and self.actual_finish and self.actual_start > self.actual_finish:
            raise ValueError("actual_start cannot be after actual_finish")
        if self.actual_finish and self.actual_finish > self.reporting_date:
            raise ValueError("actual_finish cannot be after the reporting date")
        if self.actual_start and self.actual_start > self.reporting_date:
            raise ValueError("actual_start cannot be after the reporting date")
        return self


class ActualProgressRead(ActualProgressCreate):
    id: uuid.UUID
    activity_id: uuid.UUID
    reported_by_id: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class ActivityProgressRollup(BaseModel):
    activity_id: uuid.UUID
    activity_code: str
    name: str
    wbs_path: str
    level: int
    completion_percentage: float = Field(
        description="Quantity-weighted completion of this node and its subtree."
    )
    status: ActivityStatus
    is_delayed: bool
    is_leaf: bool = Field(
        description="True when work is booked directly against this activity."
    )
    weight: float = Field(
        description=(
            "Budgeted quantity carried by this subtree, or an activity count "
            "where the plan states no budget. This is the denominator behind "
            "completion_percentage."
        )
    )


class MatchApplicationSummary(BaseModel):
    """What applying confirmed matches actually did, including the refusals."""

    schedule_id: uuid.UUID
    matches_considered: int
    records_created: int
    records_updated: int
    skipped_not_an_actual_event: int = Field(
        description=(
            "Confirmed matches whose event was a stated intention or a "
            "non-event. Never booked as actual progress."
        )
    )
    skipped_missing_event_date: int = Field(
        description="Events with no determinable date; dating them would misplace the work."
    )
    skipped_other_schedule: int = Field(
        description="Matches confirmed against an activity in a different schedule."
    )
