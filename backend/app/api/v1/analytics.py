"""Analytics API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import SCurvePoint, AnalyticsSummary
from app.services.progress import ProgressService

router = APIRouter(prefix="/projects/{project_id}/schedules/{schedule_id}/analytics", tags=["analytics"])

@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Get schedule analytics summary",
)
def get_summary(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> AnalyticsSummary:
    service = ProgressService(db)
    return service.get_summary(schedule_id)

@router.get(
    "/s-curve",
    response_model=list[SCurvePoint],
    summary="Get S-Curve timeseries data",
)
def get_s_curve(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[SCurvePoint]:
    service = ProgressService(db)
    return service.generate_s_curve(schedule_id)
