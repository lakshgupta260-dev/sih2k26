"""Orchestrating delay prediction: train, predict, explain.

The service's job is mostly to decide **which tier answers** and to make that
decision visible. The rule chain is short and stated in every response:

1. ``force_rule_based`` was asked for -> rate arithmetic.
2. No active model for this project -> rate arithmetic, and the note says what
   is missing before a model can exist.
3. An active model whose artefact will not load, or was fitted on a different
   feature set -> rate arithmetic, and the note says the artefact was rejected.
   A stale artefact must never silently produce numbers.
4. Otherwise -> the fitted model, with the rate arithmetic still attached as
   the human-readable explanation.

Point 4 is deliberate. Even when the forest supplies the probability, the
planner is shown the arithmetic: *at this rate, this many days, against this
much float*. A probability with no checkable reasoning behind it is not
something anyone should reschedule a crew on.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuditAction, PredictionMethod, RiskLevel
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.ml import baseline
from app.ml.features import FEATURE_LABELS, ActivityFeatures, FeatureBuilder
from app.ml.model import DelayModel, TrainingRefusal, train
from app.models.prediction import DelayModelVersion, DelayPrediction
from app.models.project import Project
from app.models.schedule import Activity, Schedule
from app.models.user import User
from app.repositories.prediction import (
    DelayModelVersionRepository,
    DelayPredictionRepository,
)
from app.schemas.prediction import (
    ModelMetrics,
    PredictionDetail,
    PredictionRunSummary,
    PredictRequest,
    RiskBucket,
    RiskSummary,
    TrainingOutcome,
    TrainRequest,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext

logger = get_logger(__name__)


class PredictionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.models = DelayModelVersionRepository(db)
        self.predictions = DelayPredictionRepository(db)
        self.features = FeatureBuilder(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------- scoping

    def _schedule_in_project(self, project: Project, schedule_id: uuid.UUID) -> Schedule:
        schedule = self.db.execute(
            select(Schedule).where(
                Schedule.id == schedule_id,
                Schedule.project_id == project.id,
                Schedule.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if schedule is None:
            raise NotFoundError(
                "Schedule not found.", details={"schedule_id": str(schedule_id)}
            )
        return schedule

    def _project_schedules(self, project: Project) -> list[Schedule]:
        return list(
            self.db.execute(
                select(Schedule).where(
                    Schedule.project_id == project.id,
                    Schedule.is_deleted.is_(False),
                )
            ).scalars()
        )

    # ------------------------------------------------------------- training

    def train_model(
        self,
        project: Project,
        payload: TrainRequest,
        actor: User,
        ctx: RequestContext,
    ) -> TrainingOutcome:
        """Fit on this project's completed activities, or explain the refusal."""
        if payload.schedule_id is not None:
            schedules = [self._schedule_in_project(project, payload.schedule_id)]
        else:
            schedules = self._project_schedules(project)

        rows: list[ActivityFeatures] = []
        for schedule in schedules:
            rows.extend(self.features.build_training_rows(schedule))

        outcome = train(
            rows,
            model_dir=settings.ML_MODEL_DIR,
            min_samples=settings.ML_MIN_TRAINING_SAMPLES,
            min_minority=settings.ML_MIN_MINORITY_SAMPLES,
            min_roc_auc=settings.ML_MIN_HELDOUT_ROC_AUC,
            cv_folds=settings.ML_CV_FOLDS,
            baseline_margin=settings.ML_BASELINE_MARGIN,
            n_estimators=settings.ML_N_ESTIMATORS,
            max_depth=settings.ML_MAX_DEPTH,
            min_samples_leaf=settings.ML_MIN_SAMPLES_LEAF,
            random_state=settings.ML_RANDOM_STATE,
        )

        if isinstance(outcome, TrainingRefusal):
            self.audit.record(
                action=AuditAction.MODEL_TRAIN,
                entity_type="delay_model",
                actor_user_id=actor.id,
                project_id=project.id,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
                details={
                    "promoted": False,
                    "reason": outcome.reason,
                    "labelled_activities": outcome.samples,
                    "late_samples": outcome.late_samples,
                    "on_time_samples": outcome.on_time_samples,
                    "roc_auc": (outcome.metrics or {}).get("roc_auc"),
                    "baseline_roc_auc": outcome.baseline_roc_auc,
                },
            )
            self.db.commit()
            return TrainingOutcome(
                trained=False,
                reason=outcome.reason,
                detail=outcome.detail,
                labelled_activities=outcome.samples,
                late_samples=outcome.late_samples,
                on_time_samples=outcome.on_time_samples,
                metrics=(
                    ModelMetrics(**outcome.metrics) if outcome.metrics else None
                ),
                baseline_roc_auc=outcome.baseline_roc_auc,
            )

        # Promote: retire the previous model for this scope, keeping its row.
        self.models.deactivate_for_project(project.id)
        version = self.models.create(
            project_id=project.id,
            version=outcome.version,
            kind=outcome.kind,
            artefact_path=outcome.artefact_path,
            is_active=True,
            training_samples=outcome.samples,
            late_samples=outcome.late_samples,
            on_time_samples=outcome.on_time_samples,
            train_samples=outcome.train_samples,
            test_samples=outcome.test_samples,
            roc_auc=outcome.metrics["roc_auc"],
            accuracy=outcome.metrics["accuracy"],
            precision=outcome.metrics["precision"],
            recall=outcome.metrics["recall"],
            f1=outcome.metrics["f1"],
            brier=outcome.metrics["brier"],
            baseline_roc_auc=outcome.baseline_roc_auc,
            feature_names=outcome.feature_names,
            feature_importances=outcome.feature_importances,
            hyperparameters=outcome.hyperparameters,
            trained_by_id=actor.id,
        )

        self.audit.record(
            action=AuditAction.MODEL_TRAIN,
            entity_type="delay_model",
            entity_id=version.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={
                "promoted": True,
                "version": outcome.version,
                "labelled_activities": outcome.samples,
                "roc_auc": outcome.metrics["roc_auc"],
                "recall": outcome.metrics["recall"],
            },
        )
        self.db.commit()

        return TrainingOutcome(
            trained=True,
            reason=None,
            detail=(
                f"Fitted on {outcome.samples} completed activities "
                f"({outcome.late_samples} late, {outcome.on_time_samples} on "
                f"time), sampled at several points in each activity's planned "
                f"window for {outcome.test_samples} rows, every one scored "
                f"out-of-fold. "
                f"Cross-validated ROC AUC {outcome.metrics['roc_auc']:.3f} "
                f"against {outcome.baseline_roc_auc:.3f} for the rule-based "
                f"forecast on the same activities, recall "
                f"{outcome.metrics['recall']:.3f}. Promoted as the active "
                f"model for this project."
                if outcome.baseline_roc_auc is not None else
                f"Cross-validated ROC AUC {outcome.metrics['roc_auc']:.3f}, "
                f"recall {outcome.metrics['recall']:.3f}. Promoted as the "
                f"active model for this project."
            ),
            labelled_activities=outcome.samples,
            late_samples=outcome.late_samples,
            on_time_samples=outcome.on_time_samples,
            version=outcome.version,
            kind=outcome.kind,
            train_samples=outcome.train_samples,
            test_samples=outcome.test_samples,
            metrics=ModelMetrics(**outcome.metrics),
            baseline_roc_auc=outcome.baseline_roc_auc,
            feature_importances=outcome.feature_importances,
        )

    # ----------------------------------------------------------- tier choice

    def _resolve_tier(
        self, project: Project, force_rule_based: bool
    ) -> tuple[DelayModel | None, DelayModelVersion | None, str]:
        """Pick the tier and produce the note explaining the choice."""
        if force_rule_based:
            return None, None, (
                "Rate-based forecast requested explicitly; any active fitted "
                "model was bypassed."
            )

        version = self.models.active_for_project(project.id)
        if version is None:
            return None, None, (
                "No fitted model is active for this project, so the rate-based "
                "forecast was used. Train one once enough activities have "
                "completed with both a planned and an actual finish "
                f"(at least {settings.ML_MIN_TRAINING_SAMPLES}, including "
                f"{settings.ML_MIN_MINORITY_SAMPLES} of each outcome)."
            )

        try:
            model = DelayModel.load(version.artefact_path)
        except Exception as exc:  # noqa: BLE001 - any load failure is a refusal
            logger.warning(
                "delay_model_artefact_rejected",
                extra={"version": version.version, "error": str(exc)},
            )
            return None, None, (
                f"The active model artefact ({version.version}) could not be "
                f"loaded, so the rate-based forecast was used instead rather "
                f"than scoring against something unverified. Retrain to "
                f"replace it."
            )

        note = (
            f"Fitted model {version.version} produced these probabilities. "
            f"Cross-validated ROC AUC "
            f"{version.roc_auc:.3f} across {version.test_samples} activities."
            if version.roc_auc is not None
            else f"Fitted model {version.version} produced these probabilities."
        )
        return model, version, note

    # ------------------------------------------------------------ prediction

    def run(
        self,
        project: Project,
        schedule_id: uuid.UUID,
        payload: PredictRequest,
        actor: User,
        ctx: RequestContext,
    ) -> PredictionRunSummary:
        schedule = self._schedule_in_project(project, schedule_id)
        as_of = payload.as_of or date.today()
        rows = self.features.build_for_schedule(schedule, as_of=as_of)

        model, version, note = self._resolve_tier(project, payload.force_rule_based)
        existing = self.predictions.existing_for_schedule(schedule.id)

        counts: dict[str, int] = {level.value: 0 for level in RiskLevel}
        not_forecastable = 0
        scored = 0

        for row in rows:
            # The arithmetic runs for every activity regardless of tier: it is
            # the explanation the planner reads, and the fallback when the plan
            # gives nothing to be late against.
            rule = baseline.forecast(
                row,
                as_of=as_of,
                medium=settings.ML_RISK_MEDIUM_THRESHOLD,
                high=settings.ML_RISK_HIGH_THRESHOLD,
                critical=settings.ML_RISK_CRITICAL_THRESHOLD,
            )

            if row.planned_finish is None:
                method = PredictionMethod.NOT_FORECASTABLE
                probability = 0.0
                predicted_late = False
                risk = RiskLevel.LOW
                explanation = rule.as_explanation()
                caveats = list(rule.caveats)
                not_forecastable += 1
            elif model is None:
                method = PredictionMethod.RULE_BASED_RATE
                probability = rule.probability
                predicted_late = rule.predicted_late
                risk = rule.risk_level
                explanation = rule.as_explanation()
                caveats = list(rule.caveats)
            else:
                method = PredictionMethod.RANDOM_FOREST
                probability = model.predict_probability(row)
                predicted_late = probability >= 0.5
                risk = baseline.risk_level(
                    probability,
                    settings.ML_RISK_MEDIUM_THRESHOLD,
                    settings.ML_RISK_HIGH_THRESHOLD,
                    settings.ML_RISK_CRITICAL_THRESHOLD,
                )
                explanation = rule.as_explanation()
                explanation["notable_features"] = model.notable_features(row)
                explanation["notable_features_note"] = (
                    "Inputs that are both influential in the fitted model and "
                    "unusual for this activity. An indication of what stands "
                    "out, not a decomposition of the probability."
                )
                explanation["rule_based_probability"] = round(rule.probability, 4)
                caveats = list(rule.caveats)
                if abs(probability - rule.probability) >= 0.35:
                    caveats.append(
                        "The fitted model and the rate arithmetic disagree "
                        "substantially here. Worth a look at the drivers before "
                        "acting on the number."
                    )

            counts[risk.value] = counts.get(risk.value, 0) + 1
            scored += 1

            record = existing.get(row.activity_id)
            if record is None:
                record = DelayPrediction(
                    project_id=project.id,
                    schedule_id=schedule.id,
                    activity_id=row.activity_id,
                )
                self.db.add(record)

            record.method = method
            record.model_version_id = version.id if (version and model) else None
            record.probability = probability
            record.predicted_late = predicted_late
            record.risk_level = risk
            record.planned_finish = row.planned_finish
            record.forecast_finish = rule.forecast_finish
            record.forecast_slip_days = rule.forecast_slip_days
            record.as_of = as_of
            record.features = {k: round(v, 5) for k, v in row.values.items()}
            record.explanation = explanation
            record.caveats = caveats
            record.generated_by_id = actor.id

        self.db.flush()

        run_method = (
            PredictionMethod.RANDOM_FOREST if model is not None
            else PredictionMethod.RULE_BASED_RATE
        )
        self.audit.record(
            action=AuditAction.PREDICT_RUN,
            entity_type="schedule",
            entity_id=schedule.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={
                "as_of": as_of.isoformat(),
                "method": str(run_method),
                "model_version": version.version if (version and model) else None,
                "activities_scored": scored,
                "not_forecastable": not_forecastable,
                "by_risk_level": counts,
            },
        )
        self.db.commit()

        return PredictionRunSummary(
            schedule_id=schedule.id,
            as_of=as_of,
            method=run_method,
            model_version=version.version if (version and model) else None,
            model_note=note,
            activities_scored=scored,
            not_forecastable=not_forecastable,
            by_risk_level=counts,
        )

    # ----------------------------------------------------------------- reads

    def list_predictions(
        self,
        project: Project,
        schedule_id: uuid.UUID,
        *,
        risk_level: str | None,
        predicted_late: bool | None,
        skip: int,
        limit: int,
    ):
        schedule = self._schedule_in_project(project, schedule_id)
        return self.predictions.list_for_schedule(
            schedule.id, risk_level=risk_level, predicted_late=predicted_late,
            skip=skip, limit=limit,
        )

    def get_detail(
        self, project: Project, schedule_id: uuid.UUID, activity_id: uuid.UUID
    ) -> PredictionDetail:
        schedule = self._schedule_in_project(project, schedule_id)
        activity = self.db.execute(
            select(Activity).where(
                Activity.id == activity_id, Activity.schedule_id == schedule.id
            )
        ).scalar_one_or_none()
        if activity is None:
            raise NotFoundError(
                "Activity not found.", details={"activity_id": str(activity_id)}
            )
        record = self.predictions.by_activity(activity.id)
        if record is None:
            raise NotFoundError(
                "No prediction has been generated for this activity yet.",
                details={"activity_id": str(activity_id)},
            )
        return self._detail(record, activity)

    def _detail(
        self, record: DelayPrediction, activity: Activity | None = None
    ) -> PredictionDetail:
        if activity is None:
            activity = self.db.get(Activity, record.activity_id)
        version = (
            self.db.get(DelayModelVersion, record.model_version_id)
            if record.model_version_id
            else None
        )
        return PredictionDetail(
            id=record.id,
            activity_id=record.activity_id,
            method=record.method,
            probability=record.probability,
            predicted_late=record.predicted_late,
            risk_level=record.risk_level,
            planned_finish=record.planned_finish,
            forecast_finish=record.forecast_finish,
            forecast_slip_days=record.forecast_slip_days,
            as_of=record.as_of,
            activity_code=activity.activity_code if activity else None,
            activity_name=activity.name if activity else None,
            wbs_path=activity.wbs_path if activity else None,
            model_version=version.version if version else None,
            explanation=record.explanation,
            caveats=record.caveats,
            features=record.features,
        )

    def risk_summary(
        self, project: Project, schedule_id: uuid.UUID, top: int = 10
    ) -> RiskSummary:
        schedule = self._schedule_in_project(project, schedule_id)
        counts = self.predictions.risk_counts(schedule.id)
        total = sum(counts.values())

        if total == 0:
            return RiskSummary(
                schedule_id=schedule.id,
                as_of=None,
                method=None,
                model_version=None,
                total_predictions=0,
                predicted_late=0,
                by_risk_level=[
                    RiskBucket(risk_level=level, count=0) for level in RiskLevel
                ],
                worst_forecast_slip_days=None,
                top_risks=[],
                note=(
                    "No predictions have been generated for this schedule yet. "
                    "Run the prediction endpoint first; this is not a finding "
                    "of low risk."
                ),
            )

        rows, _ = self.predictions.list_for_schedule(schedule.id, limit=top)
        late, _ = self.predictions.list_for_schedule(
            schedule.id, predicted_late=True, limit=1
        )
        late_count = self.predictions.list_for_schedule(
            schedule.id, predicted_late=True, limit=1
        )[1]
        newest = rows[0] if rows else None
        version = (
            self.db.get(DelayModelVersion, newest.model_version_id)
            if newest and newest.model_version_id
            else None
        )

        as_of = newest.as_of if newest else None
        note = (
            f"Based on {total} activity forecasts evaluated as at "
            f"{as_of.isoformat()}."
            if as_of else f"Based on {total} activity forecasts."
        )
        if as_of and (date.today() - as_of).days > 7:
            note += (
                f" These are {(date.today() - as_of).days} days old -- re-run "
                f"the prediction to reflect progress reported since."
            )

        return RiskSummary(
            schedule_id=schedule.id,
            as_of=as_of,
            method=newest.method if newest else None,
            model_version=version.version if version else None,
            total_predictions=total,
            predicted_late=late_count,
            by_risk_level=[
                RiskBucket(risk_level=level, count=counts.get(level.value, 0))
                for level in RiskLevel
            ],
            worst_forecast_slip_days=self.predictions.worst_slip(schedule.id),
            top_risks=[self._detail(row) for row in rows],
            note=note,
        )

    def list_models(
        self, project: Project, *, skip: int = 0, limit: int = 50
    ):
        return self.models.list_for_project(project.id, skip=skip, limit=limit)

    @staticmethod
    def feature_reference() -> list[dict[str, str]]:
        """What each feature means, so the explanation is readable."""
        return [
            {"feature": name, "label": label}
            for name, label in FEATURE_LABELS.items()
        ]
