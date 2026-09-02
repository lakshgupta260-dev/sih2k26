"""Planned-vs-actual analytics endpoints.

Both routes are read-only and gated on project membership. Every figure they
return is computed from ingested plan dates and reported progress; where the
data does not support a figure the field is null rather than a plausible
number.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import AccessibleProject, CurrentUser, DbSession
from app.schemas.analytics import AnalyticsSummary, SCurvePoint
from app.services.progress import ProgressService

router = APIRouter(
    prefix="/projects/{project_id}/schedules/{schedule_id}/analytics",
    tags=["analytics"],
)


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Headline schedule health figures",
    description=(
        "Quantity-weighted completion against where the plan says the job "
        "should be as of `as_of`. `schedule_variance` is actual minus planned "
        "in percentage points, negative meaning behind plan, and is null when "
        "the ingested plan carries no dates to compare against."
    ),
)
def get_summary(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
    as_of: date | None = Query(
        None, description="Evaluate as at this date instead of today."
    ),
) -> AnalyticsSummary:
    return ProgressService(db).get_summary(project, schedule_id, as_of=as_of)


@router.get(
    "/s-curve",
    response_model=list[SCurvePoint],
    summary="Cumulative planned vs actual completion over time",
    description=(
        "Weekly samples across the plan window. Planned is spread linearly "
        "within each activity's planned window, weighted by budgeted quantity "
        "-- linear because start and finish are the only distribution the "
        "ingested schedule states.\n\n"
        "`actual_percentage` is null outside the reported window: carrying the "
        "last known value forward would draw a flat line that reads as an "
        "observed stall rather than missing data. An empty list means the plan "
        "carries no dates, so there is no curve to draw."
    ),
)
def get_s_curve(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> list[SCurvePoint]:
    return ProgressService(db).generate_s_curve(project, schedule_id)
