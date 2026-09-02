"""Celery tasks for fitting the delay model and scoring a schedule.

Both are worth moving off the request path: fitting a 300-tree forest and
building features for every activity in a large schedule are CPU-bound, and a
planner clicking "predict" should not hold an HTTP connection open through it.
"""
from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.project import Project
from app.models.user import User
from app.schemas.prediction import PredictRequest, TrainRequest
from app.services.auth import RequestContext
from app.services.prediction import PredictionService
from app.worker import celery_app

logger = get_logger(__name__)


def _load(db, project_id: str, actor_user_id: str) -> tuple[Project, User] | None:
    """Re-load the project and acting user inside the worker's own session.

    The actor is passed by id and reloaded rather than serialised, so the run
    is attributed to a real user in the audit log instead of appearing to come
    from nobody.
    """
    project = db.get(Project, uuid.UUID(project_id))
    actor = db.get(User, uuid.UUID(actor_user_id))
    if project is None or actor is None:
        return None
    return project, actor


@celery_app.task(name="prediction.train_delay_model")
def train_delay_model(
    project_id: str, actor_user_id: str, *, schedule_id: str | None = None
) -> dict:
    db = SessionLocal()
    try:
        loaded = _load(db, project_id, actor_user_id)
        if loaded is None:
            logger.error("train_task_unknown_scope", extra={"project_id": project_id})
            return {"error": "unknown project or actor"}
        project, actor = loaded
        outcome = PredictionService(db).train_model(
            project,
            TrainRequest(schedule_id=uuid.UUID(schedule_id) if schedule_id else None),
            actor,
            RequestContext(user_agent="celery:prediction"),
        )
        return outcome.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - a worker must not die on one job
        db.rollback()
        logger.exception("train_task_failed", extra={"project_id": project_id})
        return {"error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="prediction.predict_schedule")
def predict_schedule(
    project_id: str,
    schedule_id: str,
    actor_user_id: str,
    *,
    force_rule_based: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        loaded = _load(db, project_id, actor_user_id)
        if loaded is None:
            logger.error("predict_task_unknown_scope", extra={"project_id": project_id})
            return {"error": "unknown project or actor"}
        project, actor = loaded
        summary = PredictionService(db).run(
            project,
            uuid.UUID(schedule_id),
            PredictRequest(force_rule_based=force_rule_based),
            actor,
            RequestContext(user_agent="celery:prediction"),
        )
        return summary.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("predict_task_failed", extra={"schedule_id": schedule_id})
        return {"error": str(exc)}
    finally:
        db.close()
