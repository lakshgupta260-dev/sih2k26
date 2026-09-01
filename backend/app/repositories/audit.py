"""Audit log persistence (append-only)."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, db: Session) -> None:
        super().__init__(AuditLog, db)

    def list_logs(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        actor_user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        action: str | None = None,
    ) -> Sequence[AuditLog]:
        stmt = select(AuditLog)
        if actor_user_id:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if project_id:
            stmt = stmt.where(AuditLog.project_id == project_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def count_logs(
        self,
        *,
        actor_user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        action: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AuditLog)
        if actor_user_id:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if project_id:
            stmt = stmt.where(AuditLog.project_id == project_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return int(self.db.execute(stmt).scalar_one())

    def update(self, instance, **values):  # noqa: ANN001, ANN201
        raise NotImplementedError("Audit logs are append-only.")

    def delete(self, instance) -> None:  # noqa: ANN001
        raise NotImplementedError("Audit logs are append-only.")
