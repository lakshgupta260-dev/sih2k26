"""The trained tier: a random forest over the features, or an honest refusal.

The hard part of this phase is not fitting a classifier. It is refusing to.

A hackathon backend can always produce a model object and a number that looks
like accuracy. What it cannot honestly do is fit on a handful of rows and
report the result as a measurement. So this module:

* trains only on **completed activities with a known planned and actual
  finish** -- real outcomes from the org's own schedules, never synthesised;
* builds each training row **as at the day before that activity finished**, so
  the outcome cannot leak in through the progress deficit (see
  :meth:`~app.ml.features.FeatureBuilder.build_training_rows`);
* refuses to train at all below configured sample and minority-class floors,
  returning the reason;
* evaluates with **stratified, group-aware cross-validation**, so every
  labelled row contributes an out-of-fold prediction rather than the estimate
  resting on one small split -- grouped by activity, because several rows are
  taken per activity at different points in its planned window and splitting
  those across folds would leak between them;
* refuses to promote a model that fails a configured ROC AUC floor;
* **refuses to promote a model that does not beat the rule-based forecast** on
  the same rows. This is the guard that matters. A homogeneous training
  population -- fifty activities of identical duration and reporting shape --
  produces near-duplicate folds and a ROC AUC of 1.000 that any floor sails
  past, while the fitted model generalises terribly to an activity of a
  different shape. Scoring the arithmetic on the same rows catches that,
  because the arithmetic does not overfit;
* reports the metrics it actually measured, with the sample counts behind
  them, and never reports a metric it could not compute.

When training refuses or the promoted model is unavailable, callers fall back
to :mod:`app.ml.baseline`, and the prediction says so. A forecast in this
system is always attributable to a named method.
"""
from __future__ import annotations

import json
import pathlib
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.ml.features import FEATURE_LABELS, FEATURE_NAMES, ActivityFeatures

logger = get_logger(__name__)

MODEL_KIND = "RANDOM_FOREST"
# Bumped when the feature set or fitting procedure changes in a way that makes
# older artefacts unusable. Artefacts record it and are rejected on mismatch.
ARTEFACT_SCHEMA_VERSION = 1


@dataclass(slots=True)
class TrainingRefusal:
    """Why no model was fitted. Not an error -- an honest outcome."""

    reason: str
    detail: str
    samples: int
    late_samples: int
    on_time_samples: int
    metrics: dict[str, float | None] | None = None
    baseline_roc_auc: float | None = None

    @property
    def trained(self) -> bool:
        return False


@dataclass(slots=True)
class TrainingResult:
    """A fitted, promoted model and the metrics measured on held-out rows."""

    version: str
    kind: str
    artefact_path: str
    feature_names: list[str]
    trained_at: datetime
    samples: int
    late_samples: int
    on_time_samples: int
    train_samples: int
    test_samples: int
    metrics: dict[str, float | None]
    baseline_roc_auc: float | None
    feature_importances: list[dict[str, Any]]
    hyperparameters: dict[str, Any]

    @property
    def trained(self) -> bool:
        return True


class DelayModel:
    """Wraps a fitted estimator and the metadata needed to trust it."""

    def __init__(
        self,
        estimator: Any,
        feature_names: list[str],
        version: str,
        metrics: dict[str, float | None],
        training_means: list[float],
        training_stds: list[float],
    ) -> None:
        self.estimator = estimator
        self.feature_names = feature_names
        self.version = version
        self.metrics = metrics
        self.training_means = training_means
        self.training_stds = training_stds

    # ---------------------------------------------------------------- predict

    def predict_probability(self, row: ActivityFeatures) -> float:
        """Probability that this activity finishes late."""
        if list(self.feature_names) != list(FEATURE_NAMES):
            raise ValueError(
                "Model was fitted on a different feature set than the running "
                "code builds; refusing to score against it."
            )
        vector = [row.vector()]
        proba = self.estimator.predict_proba(vector)[0]
        classes = list(self.estimator.classes_)
        if 1 in classes:
            return float(proba[classes.index(1)])
        # Single-class training set should have been refused upstream; if it
        # somehow reaches here, say what the model can actually assert.
        return float(1.0 if classes and classes[0] == 1 else 0.0)

    def notable_features(self, row: ActivityFeatures, limit: int = 5) -> list[dict[str, Any]]:
        """Which inputs are both influential and unusual for this activity.

        This is **not** a decomposition of the probability. It is the honest
        thing a tree ensemble can say without a SHAP dependency: rank features
        by global importance times how far this activity sits from the training
        population, and state the direction. Labelled as such in the response
        so nobody reads it as a causal attribution.
        """
        importances = getattr(self.estimator, "feature_importances_", None)
        if importances is None:
            return []
        out: list[dict[str, Any]] = []
        for index, name in enumerate(self.feature_names):
            std = self.training_stds[index]
            if std <= 0:
                continue
            value = float(row.values.get(name, 0.0))
            z = (value - self.training_means[index]) / std
            out.append({
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                "value": round(value, 4),
                "influence": round(float(importances[index]) * abs(z), 5),
                "unusualness_sigma": round(z, 2),
                "direction": "above" if z > 0 else "below",
            })
        out.sort(key=lambda d: d["influence"], reverse=True)
        return [d for d in out if d["influence"] > 0][:limit]

    # ------------------------------------------------------------ persistence

    def save(self, directory: pathlib.Path) -> pathlib.Path:
        import joblib

        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"delay-{self.version}.joblib"
        joblib.dump(
            {
                "schema_version": ARTEFACT_SCHEMA_VERSION,
                "kind": MODEL_KIND,
                "version": self.version,
                "feature_names": self.feature_names,
                "metrics": self.metrics,
                "training_means": self.training_means,
                "training_stds": self.training_stds,
                "estimator": self.estimator,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | pathlib.Path) -> DelayModel:
        import joblib

        payload = joblib.load(str(path))
        if payload.get("schema_version") != ARTEFACT_SCHEMA_VERSION:
            raise ValueError(
                f"Model artefact at {path} was written by schema version "
                f"{payload.get('schema_version')}, but this build expects "
                f"{ARTEFACT_SCHEMA_VERSION}. Retrain rather than scoring "
                f"against it."
            )
        return cls(
            estimator=payload["estimator"],
            feature_names=list(payload["feature_names"]),
            version=payload["version"],
            metrics=dict(payload["metrics"]),
            training_means=list(payload["training_means"]),
            training_stds=list(payload["training_stds"]),
        )


def train(
    rows: list[ActivityFeatures],
    *,
    model_dir: str,
    min_samples: int,
    min_minority: int,
    min_roc_auc: float,
    cv_folds: int,
    baseline_margin: float,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
    random_state: int,
) -> TrainingResult | TrainingRefusal:
    """Fit and evaluate, or refuse with a reason.

    Returns a :class:`TrainingRefusal` rather than raising, because "there is
    not enough history to learn from yet" is the expected state early in a
    project, not a failure.
    """
    import numpy as np

    labelled = [(r, r.finished_late) for r in rows]
    usable = [(r, bool(late)) for r, late in labelled if late is not None]

    # Floors are counted in **distinct activities**, not rows. Several rows are
    # taken per activity at different points in its window, and treating those
    # as independent samples would let five activities pass a forty-sample
    # floor.
    activity_outcome: dict[Any, bool] = {}
    for row, late in usable:
        activity_outcome[row.activity_id] = late
    activities = len(activity_outcome)
    late_count = sum(1 for late in activity_outcome.values() if late)
    on_time_count = activities - late_count

    if activities < min_samples:
        return TrainingRefusal(
            reason="INSUFFICIENT_SAMPLES",
            detail=(
                f"Found {activities} completed activities with both a planned "
                f"and an actual finish; at least {min_samples} are needed "
                f"before a fitted accuracy figure means anything. The "
                f"rule-based forecast is used until then."
            ),
            samples=activities,
            late_samples=late_count,
            on_time_samples=on_time_count,
        )

    minority = min(late_count, on_time_count)
    if minority < min_minority:
        scarce = "late" if late_count < on_time_count else "on-time"
        return TrainingRefusal(
            reason="INSUFFICIENT_MINORITY_CLASS",
            detail=(
                f"Only {minority} {scarce} outcomes in {activities} labelled "
                f"activities; at least {min_minority} of each class are needed. "
                f"A model fitted on this would predict the majority class and "
                f"score well doing it. The rule-based forecast is used instead."
            ),
            samples=activities,
            late_samples=late_count,
            on_time_samples=on_time_count,
        )

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score,
        brier_score_loss,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict

    X = np.asarray([r.vector() for r, _ in usable], dtype=float)
    y = np.asarray([1 if late else 0 for _, late in usable], dtype=int)
    # Rows from the same activity must land in the same fold.
    groups = np.asarray([str(r.activity_id) for r, _ in usable])

    def _forest() -> RandomForestClassifier:
        return RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            # The interesting class is usually the smaller one, and a planner
            # cares far more about a missed late finish than a false alarm.
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )

    # Cross-validation rather than one hold-out split: on a few dozen rows a
    # single 25% split makes the reported figure a coin toss about which rows
    # landed in it. Out-of-fold predictions let every row contribute while
    # still never scoring a row the model saw.
    folds = max(2, min(cv_folds, minority))
    splitter = StratifiedGroupKFold(
        n_splits=folds, shuffle=True, random_state=random_state
    )
    oof = cross_val_predict(
        _forest(), X, y, groups=groups, cv=splitter,
        method="predict_proba", n_jobs=None,
    )
    positive = oof[:, 1]
    predictions = (positive >= 0.5).astype(int)

    metrics: dict[str, float | None] = {
        "roc_auc": float(roc_auc_score(y, positive)),
        "accuracy": float(accuracy_score(y, predictions)),
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "recall": float(recall_score(y, predictions, zero_division=0)),
        "f1": float(f1_score(y, predictions, zero_division=0)),
        "brier": float(brier_score_loss(y, positive)),
    }

    # Score the rule-based forecast on exactly the same rows. It cannot overfit,
    # so it is the honest reference point -- and the check that catches a
    # homogeneous training set whose folds are near-duplicates of each other.
    baseline_auc = _baseline_roc_auc([r for r, _ in usable], y, positive.shape[0])

    if metrics["roc_auc"] < min_roc_auc:
        return TrainingRefusal(
            reason="BELOW_ACCURACY_FLOOR",
            detail=(
                f"Cross-validated ROC AUC was {metrics['roc_auc']:.3f}, below "
                f"the {min_roc_auc:.2f} floor. On this history the model does "
                f"not discriminate well enough to act on, so it is not "
                f"promoted. More completed activities, or richer progress "
                f"reporting, is what moves this."
            ),
            samples=activities,
            late_samples=late_count,
            on_time_samples=on_time_count,
            metrics=metrics,
            baseline_roc_auc=baseline_auc,
        )

    if baseline_auc is not None and metrics["roc_auc"] < baseline_auc + baseline_margin:
        return TrainingRefusal(
            reason="NOT_BETTER_THAN_BASELINE",
            detail=(
                f"Cross-validated ROC AUC was {metrics['roc_auc']:.3f} against "
                f"{baseline_auc:.3f} for the rule-based forecast on the same "
                f"activities. The model does not beat the arithmetic by the "
                f"required {baseline_margin:.2f} margin, so it is not promoted "
                f"and the rule-based forecast continues to be used. A high "
                f"cross-validated score on a set of near-identical activities "
                f"does not survive contact with an activity of a different "
                f"shape; more varied completed work is what changes this."
            ),
            samples=activities,
            late_samples=late_count,
            on_time_samples=on_time_count,
            metrics=metrics,
            baseline_roc_auc=baseline_auc,
        )

    # Evaluation is done; refit on everything for the artefact that ships.
    estimator = _forest()
    estimator.fit(X, y)

    means = X.mean(axis=0).tolist()
    stds = X.std(axis=0).tolist()
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]

    model = DelayModel(
        estimator=estimator,
        feature_names=list(FEATURE_NAMES),
        version=version,
        metrics=metrics,
        training_means=means,
        training_stds=stds,
    )
    path = model.save(pathlib.Path(model_dir))

    importances = sorted(
        (
            {
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                "importance": round(float(value), 5),
            }
            for name, value in zip(FEATURE_NAMES, estimator.feature_importances_)
        ),
        key=lambda d: d["importance"],
        reverse=True,
    )

    logger.info(
        "delay_model_trained",
        extra={
            "version": version,
            "samples": activities,
            "roc_auc": metrics["roc_auc"],
            "baseline_roc_auc": baseline_auc,
        },
    )

    return TrainingResult(
        version=version,
        kind=MODEL_KIND,
        artefact_path=str(path),
        feature_names=list(FEATURE_NAMES),
        trained_at=datetime.now(timezone.utc),
        samples=activities,
        late_samples=late_count,
        on_time_samples=on_time_count,
        # Rows, not activities: several are taken per activity at different
        # points in its window. Every row is scored out-of-fold.
        train_samples=int(len(y) - len(y) // folds),
        test_samples=int(len(y)),
        metrics=metrics,
        baseline_roc_auc=baseline_auc,
        feature_importances=importances,
        hyperparameters={
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "min_samples_leaf": min_samples_leaf,
            "class_weight": "balanced",
            "cv_folds": folds,
            "baseline_margin": baseline_margin,
            "random_state": random_state,
        },
    )


def _baseline_roc_auc(
    rows: list[ActivityFeatures], y, _n: int
) -> float | None:
    """ROC AUC of the rule-based forecast on the same labelled rows.

    Imported lazily and locally to keep :mod:`app.ml.baseline` and this module
    free of a circular import. Returns ``None`` when the arithmetic produces a
    single constant probability across every row, since AUC is then undefined
    and there is nothing to compare against.
    """
    from sklearn.metrics import roc_auc_score

    from app.ml import baseline as baseline_module

    probabilities = []
    for row in rows:
        as_of = row.as_of
        if as_of is None:
            return None
        # Bands do not affect the probability, only the label it maps to.
        result = baseline_module.forecast(
            row, as_of=as_of, medium=0.35, high=0.60, critical=0.80
        )
        probabilities.append(result.probability)

    if len(set(probabilities)) < 2:
        return None
    try:
        return float(roc_auc_score(y, probabilities))
    except ValueError:
        return None
