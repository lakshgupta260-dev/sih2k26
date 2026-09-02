"""Delay prediction request and response shapes."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import PredictionMethod, RiskLevel


class TrainRequest(BaseModel):
    schedule_id: uuid.UUID | None = Field(
        None,
        description=(
            "Train on one schedule. Omit to train on every schedule in the "
            "project, which is usually what you want -- more completed "
            "activities means a figure worth reporting."
        ),
    )


class ModelMetrics(BaseModel):
    """Cross-validated figures, computed on out-of-fold predictions.

    Null means the metric could not be computed from the rows available, which
    is a different statement from a value of zero.
    """

    roc_auc: float | None = None
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    brier: float | None = Field(
        None, description="Mean squared error of the probabilities. Lower is better."
    )


class TrainingOutcome(BaseModel):
    """Either a promoted model or a stated refusal. Never a silent fallback."""

    trained: bool
    reason: str | None = Field(
        None,
        description=(
            "Why no model was promoted: INSUFFICIENT_SAMPLES, "
            "INSUFFICIENT_MINORITY_CLASS, BELOW_ACCURACY_FLOOR or "
            "NOT_BETTER_THAN_BASELINE. Null when training succeeded."
        ),
    )
    detail: str = Field(description="Plain-language explanation of the outcome.")

    labelled_activities: int = Field(
        description="Completed activities with both a planned and an actual finish."
    )
    late_samples: int
    on_time_samples: int

    version: str | None = None
    kind: str | None = None
    train_samples: int | None = Field(
        None, description="Rows the model saw per fold."
    )
    test_samples: int | None = Field(
        None,
        description=(
            "Total rows scored out-of-fold. Larger than "
            "`labelled_activities` because several rows are taken per "
            "activity, at different points in its planned window."
        ),
    )
    metrics: ModelMetrics | None = Field(
        None,
        description=(
            "Cross-validated figures. Present even on a refusal that got far "
            "enough to measure them, so the reason can be checked."
        ),
    )
    baseline_roc_auc: float | None = Field(
        None,
        description=(
            "What the rule-based forecast scored on the same activities. The "
            "model is only promoted if it beats this by the configured margin."
        ),
    )
    feature_importances: list[dict[str, Any]] | None = Field(
        None,
        description="Global importance per feature, from the fitted forest.",
    )


class ModelVersionRead(BaseModel):
    id: uuid.UUID
    version: str
    kind: str
    is_active: bool
    trained_at: datetime = Field(validation_alias="created_at")
    training_samples: int
    late_samples: int
    on_time_samples: int
    train_samples: int
    test_samples: int = Field(description="Rows scored out-of-fold.")
    roc_auc: float | None
    accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    brier: float | None
    baseline_roc_auc: float | None
    feature_importances: list[dict[str, Any]]
    hyperparameters: dict[str, Any]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PredictRequest(BaseModel):
    as_of: date | None = Field(
        None,
        description=(
            "Evaluate the forecast as at this date instead of today. Useful "
            "for reproducing a past run."
        ),
    )
    force_rule_based: bool = Field(
        False,
        description=(
            "Skip the fitted model even when one is active, and use the "
            "rate-based forecast. Handy for comparing the two."
        ),
    )


class PredictionRunSummary(BaseModel):
    schedule_id: uuid.UUID
    as_of: date
    method: PredictionMethod = Field(
        description="The tier used for this run. Stated, never inferred."
    )
    model_version: str | None = Field(
        None, description="Null when the rule-based tier produced the run."
    )
    model_note: str = Field(
        description=(
            "Why this tier was used -- including, when no model is active, "
            "what is missing before one can be."
        )
    )
    activities_scored: int
    not_forecastable: int = Field(
        description="Activities whose plan carries no finish date to be late against."
    )
    by_risk_level: dict[str, int]


class PredictionRead(BaseModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    method: PredictionMethod
    probability: float
    predicted_late: bool
    risk_level: RiskLevel
    planned_finish: date | None
    forecast_finish: date | None
    forecast_slip_days: int | None
    as_of: date

    model_config = ConfigDict(from_attributes=True)


class PredictionDetail(PredictionRead):
    """A prediction with everything needed to argue with it."""

    activity_code: str | None = None
    activity_name: str | None = None
    wbs_path: str | None = None
    model_version: str | None = None
    explanation: dict[str, Any] = Field(
        description=(
            "For the rule-based tier, the arithmetic as named drivers. For the "
            "fitted tier, the same drivers plus `notable_features` -- inputs "
            "that are both influential and unusual for this activity. Those "
            "are an indication of which inputs stand out, not a decomposition "
            "of the probability."
        )
    )
    caveats: list[str] = Field(
        description="Where the forecast is on thin data, said plainly."
    )
    features: dict[str, Any] = Field(
        description="The feature values the forecast was computed from."
    )


class RiskBucket(BaseModel):
    risk_level: RiskLevel
    count: int


class RiskSummary(BaseModel):
    schedule_id: uuid.UUID
    as_of: date | None
    method: PredictionMethod | None = Field(
        None, description="Null when nothing has been predicted yet."
    )
    model_version: str | None = None
    total_predictions: int
    predicted_late: int
    by_risk_level: list[RiskBucket]
    worst_forecast_slip_days: int | None = None
    top_risks: list[PredictionDetail] = Field(
        description="Highest-probability activities, worst first."
    )
    note: str = Field(
        description="What this summary is based on, including if it is stale."
    )
