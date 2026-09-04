"""Model registry and stored delay predictions.

Both tables exist so a forecast a planner acted on months ago can still be
explained: which method produced it, which fitted artefact, what that artefact
measured on held-out data, and what the inputs looked like at the time. A
prediction whose provenance cannot be reconstructed is not auditable, and an
unauditable forecast is not one anybody should be making decisions on.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PredictionMethod, RiskLevel
from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DelayModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One fitted, promoted model artefact.

    Refused training attempts are not recorded here -- there is no artefact to
    register. The refusal and its reason go to the audit log instead, so the
    registry only ever contains models that were actually evaluated and passed.
    """

    __tablename__ = "delay_model_versions"
    __table_args__ = (
        UniqueConstraint("version", name="uq_delay_model_version"),
        Index("ix_delay_model_project_active", "project_id", "is_active"),
        CheckConstraint(
            "roc_auc IS NULL OR (roc_auc >= 0 AND roc_auc <= 1)", name="roc_auc_range"
        ),
        CheckConstraint("training_samples > 0", name="training_samples_positive"),
    )

    # Null means fitted across every schedule the trainer was given, rather
    # than scoped to one project.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    artefact_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Only one model per scope is served at a time; the rest are kept so an
    # older prediction still resolves to the artefact that produced it.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    training_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    late_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    on_time_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    train_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    test_samples: Mapped[int] = mapped_column(Integer, nullable=False)

    # Held-out figures, stored individually because these are the numbers
    # anyone deciding whether to trust the model will look at first.
    roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    brier: Mapped[float | None] = mapped_column(Float, nullable=True)
    # What the rule-based forecast scored on the same activities. Stored so the
    # promotion decision stays checkable after the fact.
    baseline_roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)

    feature_names: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    feature_importances: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    trained_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )


class DelayPrediction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current delay forecast for one activity.

    One row per activity: a re-run replaces the forecast rather than
    accumulating a history, because the question "what is the risk on this
    activity" has one current answer. The audit log records each run.
    """

    __tablename__ = "delay_predictions"
    __table_args__ = (
        UniqueConstraint("activity_id", name="uq_delay_prediction_activity"),
        Index("ix_delay_predictions_schedule_risk", "schedule_id", "risk_level"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1", name="probability_range"
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Which tier produced this. Never inferred by a client from the presence of
    # other fields -- the method is stated.
    method: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PredictionMethod.RULE_BASED_RATE, index=True
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("delay_model_versions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_late: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RiskLevel.LOW, index=True
    )

    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    forecast_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    forecast_slip_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The date the forecast was evaluated at, and the inputs as at that date.
    # Kept so a stale prediction is visibly stale rather than silently wrong.
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    caveats: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    model_version: Mapped["DelayModelVersion | None"] = relationship()
