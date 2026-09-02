"""APIs for user notifications and multi-channel dispatch."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.reporting import NotificationCreate, NotificationRead
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])
project_notifications_router = APIRouter(
    prefix="/projects/{project_id}/notifications", tags=["notifications"]
)


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination,
    unread_only: bool = Query(default=False),
) -> Page[NotificationRead]:
    items, total = NotificationService(db).list_user_notifications(
        current_user.id, unread_only=unread_only, skip=page.skip, limit=page.limit
    )
    return Page(
        items=[NotificationRead.model_validate(x) for x in items],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )


@router.get("/unread-count", response_model=dict[str, int])
def get_unread_count(
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, int]:
    count = NotificationService(db).get_unread_count(current_user.id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    notification = NotificationService(db).mark_as_read(notification_id, current_user.id)
    return NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=dict[str, int])
def mark_all_notifications_read(
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, int]:
    count = NotificationService(db).mark_all_as_read(current_user.id)
    return {"updated_count": count}


@project_notifications_router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def send_project_notification(
    project_id: uuid.UUID,
    body: NotificationCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    notification = NotificationService(db).send_project_notification(
        project_id=project_id, create_in=body, sender_user=current_user
    )
    return NotificationRead.model_validate(notification)
