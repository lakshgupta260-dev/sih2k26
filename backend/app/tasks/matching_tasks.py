"""Celery task running extraction and matching for a whole project."""
from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.matching import MatchRunRequest
from app.services.auth import RequestContext
from app.services.matching import MatchingService
from app.worker import celery_app

logger = get_logger(__name__)


@celery_app.task(name="matching.run_project_matching")
def run_project_matching(
    project_id: str,
    actor_user_id: str,
    *,
    schedule_id: str | None = None,
    reprocess: bool = False,
) -> dict:
    """Match every unprocessed report in a project.

    Opens its own session, as a worker process must. The acting user is passed
    by id and re-loaded here so the run is attributed correctly in the audit
    log rather than appearing to come from nobody.
    """
    db = SessionLocal()
    try:
        actor = db.get(User, uuid.UUID(actor_user_id))
        if actor is None:
            logger.error("matching_task_unknown_actor", extra={"actor": actor_user_id})
            return {"error": "unknown actor"}
        summary = MatchingService(db).run(
            uuid.UUID(project_id),
            MatchRunRequest(
                schedule_id=uuid.UUID(schedule_id) if schedule_id else None,
                reprocess=reprocess,
            ),
            actor,
            RequestContext(user_agent="celery:matching"),
        )
        return summary.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("matching_task_failed", extra={"project_id": project_id})
        return {"error": str(exc)}
    finally:
        db.close()
