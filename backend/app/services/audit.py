"""Audit trail service.

Every consequential action routes through :meth:`AuditService.record`. Audit
writes join the caller's transaction deliberately: if the action rolls back,
its audit row must roll back with it, otherwise the log would claim things
happened that did not.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import AuditAction
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)

    def record(
        self,
        *,
        action: AuditAction | str,
        entity_type: str,
        entity_id: str | uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        return self.repo.create(
            action=str(action),
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            actor_user_id=actor_user_id,
            project_id=project_id,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:400] or None,
            details=details or {},
        )
