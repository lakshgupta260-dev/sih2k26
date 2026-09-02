"""Training: what gets promoted, and — more importantly — what gets refused.

The interesting behaviour of this module is its unwillingness to hand back a
number. A backend that always produces a "trained model" and an accuracy
figure is easy; one that says "40 completed activities is not enough for this
to mean anything" is what makes the figure trustworthy when it does appear.
"""
from __future__ import annotations

import pathlib
import uuid

import pytest

from app.core.constants import ActivityStatus
from app.ml.features import FEATURE_NAMES, ActivityFeatures
from app.ml.model import DelayModel, TrainingRefusal, train

DEFAULTS = dict(
    min_samples=40,
    min_minority=8,
    min_roc_auc=0.60,
    cv_folds=5,
    # Most cases here are about the sample/accuracy floors, so the baseline
    # comparison is disabled by default and given its own dedicated tests.
    baseline_margin=0.0,
    n_estimators=60,
    max_depth=6,
    min_samples_leaf=2,
    random_state=42,
)


def _row(*, late: bool | None, rate_ratio: float, deficit: float) -> ActivityFeatures:
    """A labelled row where `rate_ratio` genuinely carries the signal."""
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["rate_ratio"] = rate_ratio
    values["rate_ratio_known"] = 1.0
    values["progress_deficit"] = deficit
    values["percent_complete"] = 0.5
    values["planned_duration_days"] = 60.0
    values["planned_duration_known"] = 1.0

    from datetime import date

    row = ActivityFeatures(
        activity_id=uuid.uuid4(), activity_code="A1", name="Task",
        wbs_path="1.1", values=values, as_of=date(2026, 2, 15),
    )
    if late is None:
        row.status = ActivityStatus.IN_PROGRESS
        return row

    row.status = ActivityStatus.COMPLETED
    row.planned_finish = date(2026, 3, 1)
    row.actual_finish = date(2026, 4, 1) if late else date(2026, 2, 20)
    return row


def _learnable_set(n_late: int = 40, n_ontime: int = 40) -> list[ActivityFeatures]:
    """A separable population: late activities ran under pace, on-time ones over.

    Deliberately learnable, because the point of these tests is the promotion
    and refusal machinery, not whether a forest can find a signal that is
    there.
    """
    rows: list[ActivityFeatures] = []
    for i in range(n_late):
        rows.append(_row(late=True, rate_ratio=0.2 + (i % 5) * 0.04,
                         deficit=-0.3 - (i % 4) * 0.05))
    for i in range(n_ontime):
        rows.append(_row(late=False, rate_ratio=1.4 + (i % 5) * 0.04,
                         deficit=0.1 + (i % 4) * 0.05))
    return rows


# ------------------------------------------------------------------ refusals

def test_too_few_labelled_activities_is_refused_with_a_reason(tmp_path):
    outcome = train(_learnable_set(6, 6), model_dir=str(tmp_path), **DEFAULTS)
    assert isinstance(outcome, TrainingRefusal)
    assert outcome.trained is False
    assert outcome.reason == "INSUFFICIENT_SAMPLES"
    assert outcome.samples == 12
    assert "at least 40" in outcome.detail
    assert "rule-based forecast" in outcome.detail


def test_unlabelled_rows_do_not_count_towards_the_sample_floor(tmp_path):
    """Activities still running carry no truth and must not pad the count."""
    rows = _learnable_set(5, 5) + [
        _row(late=None, rate_ratio=0.5, deficit=-0.1) for _ in range(100)
    ]
    outcome = train(rows, model_dir=str(tmp_path), **DEFAULTS)
    assert isinstance(outcome, TrainingRefusal)
    assert outcome.samples == 10


def test_a_lopsided_outcome_set_is_refused(tmp_path):
    """80 on-time and 3 late: a model fitted here predicts 'on time' always
    and scores 96% doing it."""
    outcome = train(_learnable_set(3, 80), model_dir=str(tmp_path), **DEFAULTS)
    assert isinstance(outcome, TrainingRefusal)
    assert outcome.reason == "INSUFFICIENT_MINORITY_CLASS"
    assert outcome.late_samples == 3
    assert "predict the majority class" in outcome.detail


def test_an_unlearnable_population_is_not_promoted(tmp_path):
    """Labels assigned with no relationship to the features. The floor must
    catch this rather than shipping a coin flip."""
    rows: list[ActivityFeatures] = []
    for i in range(60):
        # Identical feature distributions for both classes.
        rows.append(_row(late=i % 2 == 0, rate_ratio=0.9, deficit=0.0))
    outcome = train(rows, model_dir=str(tmp_path), **DEFAULTS)
    assert isinstance(outcome, TrainingRefusal)
    assert outcome.reason == "BELOW_ACCURACY_FLOOR"
    # The measured figure is reported alongside the refusal so it is checkable.
    assert outcome.metrics is not None
    assert outcome.metrics["roc_auc"] < 0.60


def test_the_accuracy_floor_is_honoured(tmp_path):
    """A floor of 1.0 cannot be met by anything short of perfection."""
    outcome = train(
        _learnable_set(), model_dir=str(tmp_path),
        **{**DEFAULTS, "min_roc_auc": 1.0},
    )
    if isinstance(outcome, TrainingRefusal):
        assert outcome.reason == "BELOW_ACCURACY_FLOOR"
        assert "floor" in outcome.detail
    else:
        # Perfect separation is possible on this synthetic set; if so the
        # metric must genuinely be 1.0 rather than rounded up to it.
        assert outcome.metrics["roc_auc"] == 1.0


# ---------------------------------------------------------------- promotion

def test_a_learnable_population_is_fitted_and_evaluated(tmp_path):
    outcome = train(_learnable_set(), model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(outcome, TrainingRefusal), getattr(outcome, "detail", "")
    assert outcome.trained is True
    assert outcome.samples == 80
    assert outcome.late_samples == 40
    assert outcome.on_time_samples == 40
    # The reported metrics come from held-out rows, and the counts add up.
    # Cross-validated: every row is scored out-of-fold.
    assert outcome.test_samples == 80
    assert outcome.metrics["roc_auc"] >= DEFAULTS["min_roc_auc"]
    assert 0.0 <= outcome.metrics["brier"] <= 1.0
    assert pathlib.Path(outcome.artefact_path).exists()


def test_importances_are_reported_and_the_real_signal_ranks_top(tmp_path):
    outcome = train(_learnable_set(), model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(outcome, TrainingRefusal)
    top = [d["feature"] for d in outcome.feature_importances[:3]]
    assert "rate_ratio" in top or "progress_deficit" in top
    # Every feature appears, and importances are a distribution.
    assert len(outcome.feature_importances) == len(FEATURE_NAMES)
    assert sum(d["importance"] for d in outcome.feature_importances) == pytest.approx(
        1.0, abs=0.01
    )
    # Labels are human-readable, not snake_case identifiers.
    assert outcome.feature_importances[0]["label"] != outcome.feature_importances[0]["feature"]


def test_training_is_reproducible_from_the_same_rows(tmp_path):
    rows = _learnable_set()
    first = train(rows, model_dir=str(tmp_path), **DEFAULTS)
    second = train(rows, model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(first, TrainingRefusal)
    assert not isinstance(second, TrainingRefusal)
    assert first.metrics == second.metrics


# --------------------------------------------------------------- the artefact

def test_a_saved_model_reloads_and_scores(tmp_path):
    outcome = train(_learnable_set(), model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(outcome, TrainingRefusal)

    model = DelayModel.load(outcome.artefact_path)
    assert model.version == outcome.version

    behind = _row(late=None, rate_ratio=0.2, deficit=-0.4)
    ahead = _row(late=None, rate_ratio=1.6, deficit=0.2)
    assert model.predict_probability(behind) > model.predict_probability(ahead)


def test_an_artefact_from_a_different_schema_version_is_rejected(tmp_path):
    """A stale artefact must refuse to score rather than produce numbers
    against a feature set the running code no longer builds."""
    import joblib

    path = tmp_path / "stale.joblib"
    joblib.dump({"schema_version": 0, "version": "old"}, path)
    with pytest.raises(ValueError, match="schema version"):
        DelayModel.load(path)


def test_a_model_fitted_on_other_features_refuses_to_score(tmp_path):
    outcome = train(_learnable_set(), model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(outcome, TrainingRefusal)
    model = DelayModel.load(outcome.artefact_path)
    model.feature_names = ["something", "else"]
    with pytest.raises(ValueError, match="different feature set"):
        model.predict_probability(_row(late=None, rate_ratio=1.0, deficit=0.0))


def test_notable_features_flag_influential_and_unusual_inputs(tmp_path):
    outcome = train(_learnable_set(), model_dir=str(tmp_path), **DEFAULTS)
    assert not isinstance(outcome, TrainingRefusal)
    model = DelayModel.load(outcome.artefact_path)

    extreme = _row(late=None, rate_ratio=0.05, deficit=-0.9)
    notable = model.notable_features(extreme)
    assert notable
    assert all(set(d) >= {"feature", "label", "value", "influence", "direction"}
               for d in notable)
    # Sorted by influence, descending.
    influences = [d["influence"] for d in notable]
    assert influences == sorted(influences, reverse=True)


# ------------------------------------------------- the baseline comparison

def _homogeneous_set(n: int = 60) -> list[ActivityFeatures]:
    """The failure the live walkthrough exposed.

    Every activity has the same planned duration and one of two reporting
    shapes, so the cross-validation folds are near-duplicates of one another.
    The forest separates them perfectly and reports a ROC AUC of 1.000 — a
    figure no accuracy floor can reject — while generalising terribly to an
    activity of any other shape.
    """
    from datetime import date

    rows: list[ActivityFeatures] = []
    for i in range(n):
        late = i % 2 == 0
        values = {name: 0.0 for name in FEATURE_NAMES}
        values["planned_duration_days"] = 40.0
        values["planned_duration_known"] = 1.0
        values["elapsed_fraction"] = 0.97
        values["days_remaining"] = 1.0
        values["percent_complete"] = 0.12 if late else 0.70
        values["planned_percent_complete"] = 0.97
        values["progress_deficit"] = values["percent_complete"] - 0.97
        values["achieved_rate_per_day"] = 0.006 if late else 0.035
        values["required_rate_per_day"] = 0.88 if late else 0.30
        values["rate_ratio"] = values["achieved_rate_per_day"] / values["required_rate_per_day"]
        values["rate_ratio_known"] = 1.0
        values["report_count"] = 2.0
        values["reporting_gap_known"] = 1.0
        values["is_started"] = 1.0

        row = ActivityFeatures(
            activity_id=uuid.uuid4(), activity_code=f"H{i:03d}", name="Section",
            wbs_path=f"1.{i}", values=values, as_of=date(2026, 2, 9),
        )
        row.status = ActivityStatus.COMPLETED
        row.planned_finish = date(2026, 2, 10)
        row.actual_finish = date(2026, 3, 7) if late else date(2026, 2, 7)
        row.completed_fraction = values["percent_complete"]
        row.achieved_rate = values["achieved_rate_per_day"]
        row.required_rate = values["required_rate_per_day"]
        row.days_remaining = 1
        row.report_count = 2
        row.budgeted_quantity = 1000.0
        row.uom = "m"
        rows.append(row)
    return rows


def test_a_flattering_score_on_near_identical_activities_is_not_promoted(tmp_path):
    """The guard the accuracy floor cannot provide.

    The model scores near-perfectly here, so BELOW_ACCURACY_FLOOR will never
    fire. It is refused because the rule-based arithmetic does just as well on
    the same rows without any fitting, which means the model has learned the
    shape of this population rather than anything about lateness.
    """
    outcome = train(
        _homogeneous_set(), model_dir=str(tmp_path),
        **{**DEFAULTS, "baseline_margin": 0.02},
    )
    assert isinstance(outcome, TrainingRefusal), (
        "a model that only matches the arithmetic on near-duplicate rows was promoted"
    )
    assert outcome.reason == "NOT_BETTER_THAN_BASELINE"
    # The refusal shows both figures so the decision can be checked.
    assert outcome.metrics["roc_auc"] >= 0.95
    assert outcome.baseline_roc_auc is not None
    assert outcome.metrics["roc_auc"] < outcome.baseline_roc_auc + 0.02
    assert "does not beat the arithmetic" in outcome.detail


def test_the_baseline_figure_is_reported_on_a_promoted_model(tmp_path):
    """A promoted model states what it was measured against."""
    outcome = train(
        _learnable_set(), model_dir=str(tmp_path),
        **{**DEFAULTS, "baseline_margin": 0.0},
    )
    assert not isinstance(outcome, TrainingRefusal), getattr(outcome, "detail", "")
    assert outcome.metrics["roc_auc"] is not None
    # Either the arithmetic was scoreable and the model matched or beat it, or
    # it produced one constant probability and there was nothing to compare to.
    if outcome.baseline_roc_auc is not None:
        assert outcome.metrics["roc_auc"] >= outcome.baseline_roc_auc


def test_a_margin_the_model_cannot_clear_blocks_promotion(tmp_path):
    """An impossible margin refuses everything, which is the correct
    behaviour for a knob set to demand more than 1.0 ROC AUC."""
    outcome = train(
        _learnable_set(), model_dir=str(tmp_path),
        **{**DEFAULTS, "baseline_margin": 0.5},
    )
    if isinstance(outcome, TrainingRefusal):
        assert outcome.reason in ("NOT_BETTER_THAN_BASELINE", "BELOW_ACCURACY_FLOOR")
    else:
        # Only acceptable if the arithmetic could not be scored at all.
        assert outcome.baseline_roc_auc is None


def test_the_comparison_is_skipped_when_the_arithmetic_cannot_be_scored(tmp_path):
    """Rows with no as-of date give the baseline nothing to work from, so the
    comparison is skipped rather than guessed at."""
    rows = _learnable_set()
    for row in rows:
        row.as_of = None
    outcome = train(
        rows, model_dir=str(tmp_path), **{**DEFAULTS, "baseline_margin": 0.5}
    )
    assert not isinstance(outcome, TrainingRefusal), getattr(outcome, "detail", "")
    assert outcome.baseline_roc_auc is None
