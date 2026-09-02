"""Delay prediction endpoints.

Every response states which tier produced it and why. There is no path
through this router that returns a probability without naming its method.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import (
    AccessibleProject,
    Ctx,
    CurrentUser,
    DbSession,
    ManagedProject,
    Pagination,
)
from app.core.constants import RiskLevel
from app.schemas.common import Page
from app.schemas.prediction import (
    ModelVersionRead,
    PredictionDetail,
    PredictionRead,
    PredictionRunSummary,
    PredictRequest,
    RiskSummary,
    TrainingOutcome,
    TrainRequest,
)
from app.services.prediction import PredictionService

router = APIRouter(prefix="/projects/{project_id}", tags=["prediction"])


@router.post(
    "/ml/train",
    response_model=TrainingOutcome,
    status_code=status.HTTP_200_OK,
    summary="Fit a delay model on completed activities, or explain the refusal",
    description=(
        "Trains on this project's completed activities that have both a "
        "planned and an actual finish -- real outcomes, never synthesised. "
        "Each training row is built as at the day *before* its activity "
        "finished, so the outcome cannot leak in through the progress "
        "deficit.\n\n"
        "`trained: false` is a normal outcome, not an error: early in a "
        "project there is not enough history for a fitted accuracy figure to "
        "mean anything, and `reason` says which floor was not met. A model is "
        "promoted only after beating a ROC AUC floor on a held-out stratified "
        "split, and the metrics reported are the ones actually measured.\n\n"
        "Requires the project manager role."
    ),
)
def train_model(
    payload: TrainRequest,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> TrainingOutcome:
    return PredictionService(db).train_model(project, payload, current_user, ctx)


@router.get(
    "/ml/models",
    response_model=Page[ModelVersionRead],
    summary="Model registry, newest first",
    description=(
        "Every promoted model with the held-out metrics behind it, so a "
        "prediction can be traced to the artefact that made it. Retired "
        "versions are kept rather than deleted."
    ),
)
def list_models(
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
    pagination: Pagination,
) -> Page[ModelVersionRead]:
    rows, total = PredictionService(db).list_models(
        project, skip=pagination.skip, limit=pagination.limit
    )
    return Page(
        items=[ModelVersionRead.model_validate(r) for r in rows],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
    )


@router.get(
    "/ml/features",
    response_model=list[dict[str, str]],
    summary="What each model feature means",
)
def feature_reference(
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> list[dict[str, str]]:
    return PredictionService(db).feature_reference()


@router.post(
    "/schedules/{schedule_id}/ml/predict",
    response_model=PredictionRunSummary,
    status_code=status.HTTP_200_OK,
    summary="Forecast a late finish for every activity in the schedule",
    description=(
        "Uses the active fitted model when one loads cleanly, and the "
        "rate-based forecast otherwise. `method` and `model_note` always say "
        "which ran and why -- including, when no model is active, what is "
        "missing before one can be.\n\n"
        "The rate arithmetic is computed either way and attached as the "
        "explanation, so there is always a checkable reason behind the "
        "number. Activities whose plan carries no finish date are recorded as "
        "`NOT_FORECASTABLE` rather than given a probability.\n\n"
        "Requires the project manager role."
    ),
)
def run_prediction(
    schedule_id: uuid.UUID,
    payload: PredictRequest,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> PredictionRunSummary:
    return PredictionService(db).run(project, schedule_id, payload, current_user, ctx)


@router.get(
    "/schedules/{schedule_id}/ml/predictions",
    response_model=Page[PredictionRead],
    summary="Stored forecasts, highest probability first",
)
def list_predictions(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
    pagination: Pagination,
    risk_level: RiskLevel | None = Query(None, description="Filter to one risk band."),
    predicted_late: bool | None = Query(
        None, description="Filter to activities forecast late, or forecast on time."
    ),
) -> Page[PredictionRead]:
    rows, total = PredictionService(db).list_predictions(
        project, schedule_id,
        risk_level=risk_level.value if risk_level else None,
        predicted_late=predicted_late,
        skip=pagination.skip, limit=pagination.limit,
    )
    return Page(
        items=[PredictionRead.model_validate(r) for r in rows],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
    )


@router.get(
    "/schedules/{schedule_id}/ml/predictions/{activity_id}",
    response_model=PredictionDetail,
    summary="One forecast with its drivers, caveats and inputs",
)
def get_prediction(
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> PredictionDetail:
    return PredictionService(db).get_detail(project, schedule_id, activity_id)


@router.get(
    "/schedules/{schedule_id}/ml/risk-summary",
    response_model=RiskSummary,
    summary="Risk bands and the worst activities on the schedule",
    description=(
        "An empty summary means nothing has been predicted yet and says so; "
        "it is not a finding of low risk. A summary older than a week says "
        "how stale it is."
    ),
)
def risk_summary(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
    top: int = Query(10, ge=1, le=50, description="How many worst activities to list."),
) -> RiskSummary:
    return PredictionService(db).risk_summary(project, schedule_id, top=top)
