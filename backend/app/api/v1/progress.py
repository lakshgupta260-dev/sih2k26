"""Progress API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.progress import ActualProgressCreate, ActualProgressRead, ActivityProgressRollup
from app.services.progress import ProgressService

router = APIRouter(prefix="/projects/{project_id}/schedules/{schedule_id}", tags=["progress"])

@router.post(
    "/activities/{activity_id}/progress",
    response_model=ActualProgressRead,
    summary="Record progress for an activity",
)
def record_progress(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    payload: ActualProgressCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ActualProgressRead:
    service = ProgressService(db)
    progress = service.record_progress(activity_id, payload, current_user)
    return ActualProgressRead.model_validate(progress)

@router.get(
    "/activities/{activity_id}/progress",
    response_model=list[ActualProgressRead],
    summary="Get progress history for an activity",
)
def get_progress_history(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[ActualProgressRead]:
    service = ProgressService(db)
    history = service.get_progress_history(activity_id)
    return [ActualProgressRead.model_validate(p) for p in history]

@router.get(
    "/progress/rollup",
    response_model=list[ActivityProgressRollup],
    summary="Get WBS progress rollup",
)
def get_progress_rollup(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[ActivityProgressRollup]:
    service = ProgressService(db)
    return service.get_project_rollup(schedule_id)
