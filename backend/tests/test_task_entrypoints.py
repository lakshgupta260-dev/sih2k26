"""The Celery task entry points, which had no test coverage at all.

Coverage before this module: ``matching_tasks.py`` 0%, ``prediction_tasks.py``
0%. Both are background job entry points, and an untested background task is
precisely where a silent failure lives -- Phase 3/4 found two of them
(a broker outage leaving jobs PENDING for ever, and a redelivery downgrading a
COMPLETED job to FAILED).

The contract every one of these shares, and the thing actually worth pinning:
**a task must never raise.** A raising task takes the worker process with it or
gets retried for ever depending on configuration, and either way one bad
project stops every other project's jobs. They must return an error dict
instead. So the tests below deliberately feed them nonsense.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.tasks.matching_tasks import run_project_matching
from app.tasks.prediction_tasks import predict_schedule, train_delay_model

# --------------------------------------------------------------- matching task


def test_matching_task_with_an_unknown_actor_reports_instead_of_raising(
    db: Session, monkeypatch, run_task_with_test_session
) -> None:
    """An actor id that no longer resolves must not kill the worker.

    Users get deactivated and deleted while jobs sit in the queue, so this is
    an ordinary occurrence rather than a corrupt-input edge case.
    """
    import app.tasks.matching_tasks as matching_tasks

    run_task_with_test_session(matching_tasks)

    result = run_project_matching(str(uuid.uuid4()), str(uuid.uuid4()))

    assert result == {"error": "unknown actor"}


def test_matching_task_swallows_a_service_failure(
    db: Session, monkeypatch, manager_user, run_task_with_test_session
) -> None:
    """A failure inside the service becomes a returned error, not an exception."""
    import app.tasks.matching_tasks as matching_tasks

    run_task_with_test_session(matching_tasks)

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("extraction backend unavailable")

    monkeypatch.setattr(
        "app.services.matching.MatchingService.run", _explode, raising=True
    )

    result = run_project_matching(str(uuid.uuid4()), str(manager_user.id))

    assert "error" in result
    assert "extraction backend unavailable" in result["error"]


def test_matching_task_returns_a_json_serialisable_summary(
    db: Session, monkeypatch, manager_user, test_project, run_task_with_test_session
) -> None:
    """The return value crosses a process boundary, so it must be JSON-safe.

    ``model_dump(mode="json")`` is what makes that true; a plain ``model_dump``
    would leave UUID and date objects in the dict and fail at serialisation
    time inside Celery rather than here.
    """
    import json

    import app.tasks.matching_tasks as matching_tasks

    run_task_with_test_session(matching_tasks)

    result = run_project_matching(test_project[0], str(manager_user.id))

    # Either a real summary or a handled error -- both must serialise.
    json.dumps(result)


# ------------------------------------------------------------- prediction tasks


@pytest.mark.parametrize("task", [train_delay_model, predict_schedule])
def test_prediction_tasks_with_an_unknown_scope_report_instead_of_raising(
    db: Session, monkeypatch, task, run_task_with_test_session
) -> None:
    """Unknown project or actor is a returned error for both tasks."""
    import app.tasks.prediction_tasks as prediction_tasks

    run_task_with_test_session(prediction_tasks)

    if task is predict_schedule:
        result = task(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    else:
        result = task(str(uuid.uuid4()), str(uuid.uuid4()))

    assert result == {"error": "unknown project or actor"}


def test_train_task_swallows_a_service_failure(
    db: Session, monkeypatch, manager_user, test_project, run_task_with_test_session
) -> None:
    import app.tasks.prediction_tasks as prediction_tasks

    run_task_with_test_session(prediction_tasks)

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("scikit-learn exploded")

    monkeypatch.setattr(
        "app.services.prediction.PredictionService.train_model", _explode, raising=True
    )

    result = train_delay_model(test_project[0], str(manager_user.id))

    assert "error" in result
    assert "scikit-learn exploded" in result["error"]


def test_predict_task_swallows_a_service_failure(
    db: Session, monkeypatch, manager_user, test_project, run_task_with_test_session
) -> None:
    import app.tasks.prediction_tasks as prediction_tasks

    run_task_with_test_session(prediction_tasks)

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("feature build failed")

    monkeypatch.setattr(
        "app.services.prediction.PredictionService.run", _explode, raising=True
    )

    result = predict_schedule(
        test_project[0], str(uuid.uuid4()), str(manager_user.id)
    )

    assert "error" in result
    assert "feature build failed" in result["error"]


def test_prediction_task_results_are_json_serialisable(
    db: Session, monkeypatch, manager_user, test_project, run_task_with_test_session
) -> None:
    import json

    import app.tasks.prediction_tasks as prediction_tasks

    run_task_with_test_session(prediction_tasks)

    json.dumps(train_delay_model(test_project[0], str(manager_user.id)))
    json.dumps(
        predict_schedule(test_project[0], str(uuid.uuid4()), str(manager_user.id))
    )


def test_a_malformed_uuid_does_not_escape_the_task(
    db: Session, monkeypatch, run_task_with_test_session
) -> None:
    """``uuid.UUID("not-a-uuid")`` raises ValueError inside the task body.

    It happens before the try block's first database call in some paths, so it
    is worth confirming the handler actually covers it rather than assuming the
    ``except Exception`` is positioned correctly.
    """
    import app.tasks.matching_tasks as matching_tasks
    import app.tasks.prediction_tasks as prediction_tasks

    run_task_with_test_session(matching_tasks)
    run_task_with_test_session(prediction_tasks)

    assert "error" in run_project_matching("not-a-uuid", "also-not-a-uuid")
    assert "error" in train_delay_model("not-a-uuid", "also-not-a-uuid")
    assert "error" in predict_schedule("not-a-uuid", "nope", "also-not-a-uuid")
