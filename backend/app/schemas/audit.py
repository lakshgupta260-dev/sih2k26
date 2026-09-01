"""Audit log contracts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class AuditLogRead(ORMModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    project_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    ip_address: str | None
    details: dict[str, Any]
    created_at: datetime
