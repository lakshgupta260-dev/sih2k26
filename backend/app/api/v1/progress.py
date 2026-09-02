"""Progress recording endpoints.

Every route takes a project through a guard dependency rather than reading a
raw ``project_id`` out of the path: `AccessibleProject` for reads,
`ManagedProject` for writes. The service then proves the schedule and activity
sit inside that project. A non-member gets 404 rather than 403, matching the
convention used project-wide -- 403 would confirm the project exists.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import AccessibleProject, CurrentUser, Ctx, DbSession, ManagedProject
from app.schemas.progress import (
    ActivityProgressRollup,
    ActualProgressCreate,
    ActualProgressRead,
    MatchApplicationSummary,
)
from app.services.progress import ProgressService

router = APIRouter(
    prefix="/projects/{project_id}/schedules/{schedule_id}", tags=["progress"]
)


@router.post(
    "/activities/{activity_id}/progress",
    response_model=ActualProgressRead,
    summary="Record or correct progress for an activity on a date",
    description=(
        "One record per activity per reporting date. Posting the same date "
        "again corrects that day's figure rather than appending a second "
        "contradictory one; the superseded values are kept in the audit trail."
    ),
)
def record_progress(
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    payload: ActualProgressCreate,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> ActualProgressRead:
    progress = ProgressService(db).record_progress(
        project, schedule_id, activity_id, payload, current_user, ctx
    )
    return ActualProgressRead.model_validate(progress)


@router.get(
    "/activities/{activity_id}/progress",
    response_model=list[ActualProgressRead],
    summary="Progress history for an activity, newest first",
)
def get_progress_history(
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> list[ActualProgressRead]:
    history = ProgressService(db).get_progress_history(project, schedule_id, activity_id)
    return [ActualProgressRead.model_validate(p) for p in history]


@router.get(
    "/progress/rollup",
    response_model=list[ActivityProgressRollup],
    summary="Quantity-weighted WBS progress rollup",
    description=(
        "Completion for every node, rolled up from the leaves and weighted by "
        "budgeted quantity so a long spread does not count the same as a "
        "single task. Ordered by WBS path numerically."
    ),
)
def get_progress_rollup(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> list[ActivityProgressRollup]:
    return ProgressService(db).get_project_rollup(project, schedule_id)


@router.post(
    "/progress/apply-matches",
    response_model=MatchApplicationSummary,
    status_code=status.HTTP_200_OK,
    summary="Book confirmed matches as actual progress",
    description=(
        "Closes the document -> extract -> match -> progress chain. Only "
        "auto-matched and manually confirmed links are applied. Stated "
        "intentions ('to be taken up tomorrow') and undated events are "
        "refused and counted in the response, never booked as actuals.\n\n"
        "Requires the project manager role."
    ),
)
def apply_confirmed_matches(
    schedule_id: uuid.UUID,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> MatchApplicationSummary:
    return ProgressService(db).apply_confirmed_matches(
        project, schedule_id, current_user, ctx
    )
