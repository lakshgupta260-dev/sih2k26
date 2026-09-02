"""Delay prediction through the real API: training, tiers, provenance, scoping.

The recurring assertion in this module is that a probability never arrives
without a named method behind it, and that "we don't know yet" is returned as
such rather than dressed up as a low-risk finding.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ActivityStatus, JobStatus, PredictionMethod, RiskLevel
from app.models.prediction import DelayModelVersion, DelayPrediction
from app.models.progress import ActualProgress
from app.models.schedule import Activity, Schedule
from tests.api.test_progress import make_project

TODAY = date(2026, 6, 1)


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    """Point artefact storage at a temp dir so tests never write into the repo."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MODEL_DIR", str(tmp_path / "models"))
    return tmp_path / "models"


def _schedule(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> Schedule:
    schedule = Schedule(project_id=project_id, name="Baseline",
                        uploaded_by_id=user_id, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.flush()
    return schedule


def _leaf(db: Session, schedule: Schedule, code: str, **kwargs) -> Activity:
    defaults = dict(
        schedule_id=schedule.id, activity_code=code, name=f"Activity {code}",
        wbs_path=f"1.{code}", level=6, budgeted_quantity=1000.0, uom="m",
    )
    defaults.update(kwargs)
    activity = Activity(**defaults)
    db.add(activity)
    db.flush()
    return activity


@pytest.fixture
def live_schedule(client: TestClient, auth_headers, manager_user, db: Session):
    """Three in-flight activities: one on pace, one behind, one never started."""
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "PRED")
    schedule = _schedule(db, project_id, manager_user.id)

    on_pace = _leaf(db, schedule, "OK", planned_start=date(2026, 4, 1),
                    planned_finish=date(2026, 8, 1))
    behind = _leaf(db, schedule, "BAD", planned_start=date(2026, 4, 1),
                   planned_finish=date(2026, 7, 1))
    never = _leaf(db, schedule, "NEW", planned_start=date(2026, 3, 1),
                  planned_finish=date(2026, 9, 1))

    # On pace: 500 of 1000 m in 61 days, needs 500 more in 61 days.
    db.add_all([
        ActualProgress(activity_id=on_pace.id, reporting_date=date(2026, 4, 1),
                       actual_quantity=0.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=on_pace.id, reporting_date=TODAY,
                       actual_quantity=500.0, status=ActivityStatus.IN_PROGRESS),
    ])
    # Behind: 100 of 1000 m in 61 days, needs 900 more in 30.
    db.add_all([
        ActualProgress(activity_id=behind.id, reporting_date=date(2026, 4, 1),
                       actual_quantity=0.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=behind.id, reporting_date=TODAY,
                       actual_quantity=100.0, status=ActivityStatus.IN_PROGRESS),
    ])
    db.commit()
    return {"headers": headers, "project_id": project_id, "schedule": schedule,
            "on_pace": on_pace, "behind": behind, "never": never}


@pytest.fixture
def history(client: TestClient, auth_headers, manager_user, db: Session):
    """A project whose history a model can legitimately learn something from.

    The signal here is **seasonal, not rate-based**: every activity reports the
    same modest mid-window progress, so the rate arithmetic gives them all a
    similar middling probability and discriminates barely at all. What actually
    decides the outcome is whether the planned finish falls in the monsoon --
    realistic for pipeline and civil works in the northeast, and something the
    rule-based tier only mentions as a note without moving its number.

    That is the situation where a fitted model earns its place, and it is what
    makes this fixture different from the homogeneous rate-driven population in
    ``tests/test_delay_model.py``, which the baseline guard correctly refuses.
    """
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "HIST")
    schedule = _schedule(db, project_id, manager_user.id)

    for index in range(30):
        monsoon = index % 2 == 0
        duration = 60 + (index % 5) * 8
        # Monsoon group finishes Jun-Sep; the other group finishes Nov-Feb.
        finish_month = 6 + (index % 4) if monsoon else 11 + (index % 4)
        year = 2026 if finish_month <= 12 else 2027
        if finish_month > 12:
            finish_month -= 12
        planned_finish = date(year, finish_month, 1 + (index % 20))
        start = planned_finish - timedelta(days=duration)

        activity = _leaf(db, schedule, f"H{index:03d}", planned_start=start,
                         planned_finish=planned_finish)
        # Identical progress shape for both groups: a little behind pace.
        db.add(ActualProgress(
            activity_id=activity.id, reporting_date=start,
            actual_quantity=0.0, status=ActivityStatus.IN_PROGRESS,
        ))
        for fraction in (0.25, 0.5, 0.75):
            when = start + timedelta(days=int(duration * fraction))
            db.add(ActualProgress(
                activity_id=activity.id, reporting_date=when,
                actual_quantity=round(1000 * fraction * 0.85, 1),
                status=ActivityStatus.IN_PROGRESS,
            ))
        finish = planned_finish + timedelta(days=30 if monsoon else -4)
        db.add(ActualProgress(
            activity_id=activity.id, reporting_date=finish,
            actual_quantity=1000.0, actual_finish=finish, percent_complete=100.0,
            status=ActivityStatus.COMPLETED,
        ))
    db.commit()
    return {"headers": headers, "project_id": project_id, "schedule": schedule}


def _predict_url(project_id, schedule_id) -> str:
    return f"/api/v1/projects/{project_id}/schedules/{schedule_id}/ml/predict"


def _train_url(project_id) -> str:
    return f"/api/v1/projects/{project_id}/ml/train"


# ------------------------------------------------------------------ training

def test_training_refuses_on_a_project_with_no_history_and_says_why(
    client: TestClient, live_schedule, model_dir
):
    response = client.post(
        _train_url(live_schedule["project_id"]), json={},
        headers=live_schedule["headers"],
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["trained"] is False
    assert body["reason"] == "INSUFFICIENT_SAMPLES"
    assert body["labelled_activities"] == 0
    assert body["metrics"] is None
    assert body["version"] is None
    # The refusal tells the reader what happens instead.
    assert "rule-based" in body["detail"]


def test_a_refused_training_run_registers_no_model(
    client: TestClient, live_schedule, model_dir, db: Session
):
    client.post(_train_url(live_schedule["project_id"]), json={},
                headers=live_schedule["headers"])
    assert db.execute(select(DelayModelVersion)).scalars().all() == []


def test_a_refusal_is_still_audited(
    client: TestClient, live_schedule, model_dir, db: Session
):
    from app.models.audit import AuditLog

    client.post(_train_url(live_schedule["project_id"]), json={},
                headers=live_schedule["headers"])
    entry = db.execute(
        select(AuditLog).where(AuditLog.action == "MODEL_TRAIN")
    ).scalar_one()
    assert entry.details["promoted"] is False
    assert entry.details["reason"] == "INSUFFICIENT_SAMPLES"


def test_training_on_real_history_promotes_a_model_with_measured_metrics(
    client: TestClient, history, model_dir, monkeypatch
):
    from app.core.config import settings

    # 28 completed activities; lower the floor to match what the fixture builds.
    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)

    response = client.post(_train_url(history["project_id"]), json={},
                           headers=history["headers"])
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["trained"] is True, body["detail"]
    assert body["reason"] is None
    # Counted in distinct activities, not rows: several rows are taken per
    # activity at different points in its planned window.
    assert body["labelled_activities"] == 30
    assert body["late_samples"] == 15
    assert body["on_time_samples"] == 15
    assert body["test_samples"] > body["labelled_activities"]
    assert body["metrics"]["roc_auc"] >= settings.ML_MIN_HELDOUT_ROC_AUC
    # The promotion decision is only meaningful if the arithmetic was actually
    # scored on the same rows and lost.
    assert body["baseline_roc_auc"] is not None
    assert body["metrics"]["roc_auc"] >= (
        body["baseline_roc_auc"] + settings.ML_BASELINE_MARGIN
    )
    assert "against" in body["detail"]
    assert body["feature_importances"]
    assert model_dir.exists()


def test_the_registry_lists_the_promoted_model_with_its_metrics(
    client: TestClient, history, model_dir, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)
    client.post(_train_url(history["project_id"]), json={},
                headers=history["headers"])

    response = client.get(
        f"/api/v1/projects/{history['project_id']}/ml/models",
        headers=history["headers"],
    )
    assert response.status_code == status.HTTP_200_OK
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["is_active"] is True
    assert items[0]["kind"] == "RANDOM_FOREST"
    assert items[0]["roc_auc"] is not None
    assert items[0]["baseline_roc_auc"] is not None
    assert items[0]["training_samples"] == 30


def test_retraining_retires_the_previous_model_without_deleting_it(
    client: TestClient, history, model_dir, monkeypatch, db: Session
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)
    for _ in range(2):
        client.post(_train_url(history["project_id"]), json={},
                    headers=history["headers"])

    rows = db.execute(select(DelayModelVersion)).scalars().all()
    assert len(rows) == 2
    assert sum(1 for r in rows if r.is_active) == 1


# ---------------------------------------------------------------- prediction

def test_prediction_falls_back_to_the_rate_tier_and_names_it(
    client: TestClient, live_schedule, model_dir
):
    response = client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["method"] == PredictionMethod.RULE_BASED_RATE
    assert body["model_version"] is None
    assert body["activities_scored"] == 3
    # The note explains the fallback and what would change it.
    assert "No fitted model is active" in body["model_note"]
    assert "Train one" in body["model_note"]


def test_the_activity_behind_pace_outranks_the_one_on_pace(
    client: TestClient, live_schedule, model_dir
):
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    listing = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions",
        headers=live_schedule["headers"],
    ).json()["items"]

    by_activity = {item["activity_id"]: item for item in listing}
    behind = by_activity[str(live_schedule["behind"].id)]
    on_pace = by_activity[str(live_schedule["on_pace"].id)]

    assert behind["probability"] > on_pace["probability"]
    assert behind["predicted_late"] is True
    assert on_pace["predicted_late"] is False
    # 900 m left at ~1.64 m/day cannot land by 1 July.
    assert behind["forecast_slip_days"] > 0
    assert on_pace["forecast_slip_days"] <= 0


def test_a_never_started_activity_is_flagged_from_its_late_start(
    client: TestClient, live_schedule, model_dir
):
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    detail = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions"
        f"/{live_schedule['never'].id}",
        headers=live_schedule["headers"],
    ).json()

    factors = {d["factor"] for d in detail["explanation"]["drivers"]}
    assert "not started" in factors
    assert detail["forecast_slip_days"] == 92  # 1 Mar to 1 Jun


def test_an_activity_with_no_planned_finish_is_not_forecastable(
    client: TestClient, live_schedule, model_dir, db: Session
):
    """Recorded as NOT_FORECASTABLE rather than given a probability."""
    undated = _leaf(db, live_schedule["schedule"], "UND", planned_start=None,
                    planned_finish=None)
    db.commit()

    body = client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    ).json()
    assert body["not_forecastable"] == 1

    detail = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions/{undated.id}",
        headers=live_schedule["headers"],
    ).json()
    assert detail["method"] == PredictionMethod.NOT_FORECASTABLE
    assert detail["probability"] == 0.0
    assert any("no finish date" in c for c in detail["caveats"])


def test_every_prediction_carries_its_inputs_and_reasoning(
    client: TestClient, live_schedule, model_dir
):
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    detail = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions"
        f"/{live_schedule['behind'].id}",
        headers=live_schedule["headers"],
    ).json()

    assert detail["activity_code"] == "BAD"
    assert detail["explanation"]["drivers"]
    assert detail["features"]["rate_ratio_known"] == 1.0
    assert detail["as_of"] == TODAY.isoformat()
    # The rate sentence is stated in the plan's units.
    assert "m/day" in detail["explanation"]["drivers"][0]["detail"]


def test_re_running_replaces_rather_than_accumulating(
    client: TestClient, live_schedule, model_dir, db: Session
):
    url = _predict_url(live_schedule["project_id"], live_schedule["schedule"].id)
    client.post(url, json={"as_of": TODAY.isoformat()},
                headers=live_schedule["headers"])
    client.post(url, json={"as_of": (TODAY + timedelta(days=7)).isoformat()},
                headers=live_schedule["headers"])

    rows = db.execute(select(DelayPrediction)).scalars().all()
    assert len(rows) == 3
    assert {r.as_of for r in rows} == {TODAY + timedelta(days=7)}


def test_a_trained_model_is_used_and_attributed(
    client: TestClient, history, model_dir, monkeypatch, db: Session
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)
    trained = client.post(_train_url(history["project_id"]), json={},
                          headers=history["headers"]).json()
    assert trained["trained"] is True, trained["detail"]

    # Add an in-flight activity for the model to score.
    activity = _leaf(db, history["schedule"], "LIVE",
                     planned_start=date(2026, 4, 1), planned_finish=date(2026, 7, 1))
    db.add_all([
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 4, 1),
                       actual_quantity=0.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=activity.id, reporting_date=TODAY,
                       actual_quantity=90.0, status=ActivityStatus.IN_PROGRESS),
    ])
    db.commit()

    body = client.post(
        _predict_url(history["project_id"], history["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=history["headers"],
    ).json()
    assert body["method"] == PredictionMethod.RANDOM_FOREST
    assert body["model_version"] == trained["version"]
    assert "ROC AUC" in body["model_note"]

    detail = client.get(
        f"/api/v1/projects/{history['project_id']}/schedules"
        f"/{history['schedule'].id}/ml/predictions/{activity.id}",
        headers=history["headers"],
    ).json()
    assert detail["model_version"] == trained["version"]
    # The model's number, but the rate arithmetic is still shown alongside it.
    assert detail["explanation"]["notable_features"]
    assert "not a decomposition" in detail["explanation"]["notable_features_note"]
    assert detail["explanation"]["drivers"]
    assert "rule_based_probability" in detail["explanation"]


def test_force_rule_based_bypasses_an_active_model(
    client: TestClient, history, model_dir, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)
    client.post(_train_url(history["project_id"]), json={},
                headers=history["headers"])

    body = client.post(
        _predict_url(history["project_id"], history["schedule"].id),
        json={"as_of": TODAY.isoformat(), "force_rule_based": True},
        headers=history["headers"],
    ).json()
    assert body["method"] == PredictionMethod.RULE_BASED_RATE
    assert body["model_version"] is None
    assert "requested explicitly" in body["model_note"]


def test_an_unloadable_artefact_falls_back_rather_than_guessing(
    client: TestClient, history, model_dir, monkeypatch, db: Session
):
    """A missing or corrupt artefact must never silently produce numbers."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ML_MIN_TRAINING_SAMPLES", 20)
    client.post(_train_url(history["project_id"]), json={},
                headers=history["headers"])

    version = db.execute(select(DelayModelVersion)).scalars().one()
    version.artefact_path = "/nonexistent/gone.joblib"
    db.commit()

    body = client.post(
        _predict_url(history["project_id"], history["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=history["headers"],
    ).json()
    assert body["method"] == PredictionMethod.RULE_BASED_RATE
    assert "could not be loaded" in body["model_note"]
    assert "Retrain" in body["model_note"]


# -------------------------------------------------------------- risk summary

def test_an_empty_risk_summary_says_so_rather_than_reporting_low_risk(
    client: TestClient, live_schedule, model_dir
):
    body = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/risk-summary",
        headers=live_schedule["headers"],
    ).json()
    assert body["total_predictions"] == 0
    assert body["method"] is None
    assert "not a finding of low risk" in body["note"]


def test_the_risk_summary_bands_and_ranks_the_worst_activities(
    client: TestClient, live_schedule, model_dir
):
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    body = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/risk-summary",
        headers=live_schedule["headers"],
    ).json()

    assert body["total_predictions"] == 3
    assert body["predicted_late"] >= 1
    assert {b["risk_level"] for b in body["by_risk_level"]} == {
        level.value for level in RiskLevel
    }
    assert sum(b["count"] for b in body["by_risk_level"]) == 3
    probabilities = [r["probability"] for r in body["top_risks"]]
    assert probabilities == sorted(probabilities, reverse=True)
    assert body["top_risks"][0]["activity_code"] == "BAD"


def test_a_stale_summary_reports_how_stale_it_is(
    client: TestClient, live_schedule, model_dir
):
    old = date.today() - timedelta(days=45)
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": old.isoformat()}, headers=live_schedule["headers"],
    )
    body = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/risk-summary",
        headers=live_schedule["headers"],
    ).json()
    assert "45 days old" in body["note"]


def test_predictions_can_be_filtered_by_risk_band(
    client: TestClient, live_schedule, model_dir
):
    client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={"as_of": TODAY.isoformat()}, headers=live_schedule["headers"],
    )
    base = (
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions"
    )
    late_only = client.get(
        base, params={"predicted_late": True}, headers=live_schedule["headers"]
    ).json()
    assert late_only["total"] >= 1
    assert all(item["predicted_late"] for item in late_only["items"])


# ------------------------------------------------------------------- scoping

def test_a_supervisor_cannot_train_or_predict(
    client: TestClient, auth_headers, supervisor_user, live_schedule, model_dir
):
    outsider = auth_headers(supervisor_user)
    train = client.post(_train_url(live_schedule["project_id"]), json={},
                        headers=outsider)
    assert train.status_code == status.HTTP_404_NOT_FOUND, train.text

    predict = client.post(
        _predict_url(live_schedule["project_id"], live_schedule["schedule"].id),
        json={}, headers=outsider,
    )
    assert predict.status_code == status.HTTP_404_NOT_FOUND, predict.text


def test_an_outsider_cannot_read_predictions_or_the_registry(
    client: TestClient, auth_headers, supervisor_user, live_schedule, model_dir
):
    outsider = auth_headers(supervisor_user)
    for url in (
        f"/api/v1/projects/{live_schedule['project_id']}/ml/models",
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions",
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/risk-summary",
    ):
        response = client.get(url, headers=outsider)
        assert response.status_code == status.HTTP_404_NOT_FOUND, url


def test_a_schedule_from_another_project_is_not_predictable(
    client: TestClient, live_schedule, manager_user, db: Session, model_dir
):
    other = make_project(client, live_schedule["headers"], "OTHERPRED")
    foreign = _schedule(db, other, manager_user.id)
    db.commit()

    response = client.post(
        _predict_url(live_schedule["project_id"], foreign.id),
        json={}, headers=live_schedule["headers"],
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_an_activity_with_no_prediction_yet_is_404_not_a_zero(
    client: TestClient, live_schedule, model_dir
):
    response = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/schedules"
        f"/{live_schedule['schedule'].id}/ml/predictions"
        f"/{live_schedule['behind'].id}",
        headers=live_schedule["headers"],
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_the_feature_reference_is_readable(client: TestClient, live_schedule):
    body = client.get(
        f"/api/v1/projects/{live_schedule['project_id']}/ml/features",
        headers=live_schedule["headers"],
    ).json()
    labels = {entry["feature"]: entry["label"] for entry in body}
    assert labels["rate_ratio"] == "achieved rate as a share of what is required"
    assert "progress_deficit" in labels
