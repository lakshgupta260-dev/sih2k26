"""Notification service."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.constants import NotificationChannel, NotificationStatus, UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.project import Project, ProjectMembership
from app.models.reporting import Notification
from app.models.user import User
from app.notifications.dispatcher import NotificationDispatcher
from app.schemas.reporting import NotificationCreate


class NotificationService:
    """Business logic for creating, dispatching, listing, and reading notifications."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.dispatcher = NotificationDispatcher()

    def send_notification(
        self,
        create_in: NotificationCreate,
        *,
        project_id: uuid.UUID | None = None,
    ) -> Notification:
        """Create and immediately dispatch a single notification attempt."""
        if create_in.idempotency_key:
            existing = self.db.scalar(
                select(Notification).where(
                    Notification.idempotency_key == create_in.idempotency_key
                )
            )
            if existing:
                return existing

        notification = Notification(
            project_id=project_id,
            recipient_user_id=create_in.recipient_user_id,
            channel=create_in.channel,
            status=NotificationStatus.PENDING,
            notification_type=create_in.notification_type,
            event_key=create_in.event_key,
            idempotency_key=create_in.idempotency_key,
            recipient_address=create_in.recipient_address,
            title=create_in.title,
            body=create_in.body,
            payload=create_in.payload,
        )
        self.db.add(notification)
        self.db.flush()

        self.dispatcher.dispatch(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def list_user_notifications(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Notification], int]:
        """List in-app notifications for a specific user inbox."""
        query = select(Notification).where(
            Notification.recipient_user_id == user_id,
            Notification.channel == NotificationChannel.IN_APP,
        )
        if unread_only:
            query = query.where(Notification.read_at.is_(None))

        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = self.db.scalars(
            query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
        ).all()
        return list(items), total

    def get_unread_count(self, user_id: uuid.UUID) -> int:
        """Return total unread in-app notification count for user."""
        query = select(func.count()).where(
            Notification.recipient_user_id == user_id,
            Notification.channel == NotificationChannel.IN_APP,
            Notification.read_at.is_(None),
        )
        return self.db.scalar(query) or 0

    def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification:
        """Mark a single notification as read."""
        notification = self.db.get(Notification, notification_id)
        if not notification or notification.recipient_user_id != user_id:
            raise NotFoundError("Notification not found")

        if not notification.read_at:
            notification.read_at = datetime.now(timezone.utc)
            notification.status = NotificationStatus.READ
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        """Mark all unread in-app notifications for user as read."""
        stmt = (
            update(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.channel == NotificationChannel.IN_APP,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc), status=NotificationStatus.READ)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def send_project_notification(
        self,
        project_id: uuid.UUID,
        create_in: NotificationCreate,
        sender_user: User,
    ) -> Notification:
        """Trigger a project notification (Admin or Project Manager only)."""
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found")

        if sender_user.role != UserRole.ADMIN:
            membership = self.db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == sender_user.id,
                )
            )
            if not membership or membership.role not in (UserRole.ADMIN, UserRole.PROJECT_MANAGER):
                raise PermissionDeniedError("Only project managers or admins can send project notifications")

        # A project notification must stay inside the project: without this,
        # a PM on one project could address any user id in the system (or any
        # freeform email/phone in recipient_address) using this project's
        # notification credentials, which is an open spam/phishing relay once
        # the email/WhatsApp channels are wired to a real provider.
        if create_in.recipient_user_id is not None:
            recipient_membership = self.db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == create_in.recipient_user_id,
                )
            )
            recipient_is_admin = self.db.scalar(
                select(User.role).where(User.id == create_in.recipient_user_id)
            ) == UserRole.ADMIN
            if not recipient_membership and not recipient_is_admin:
                raise ValidationError("Recipient is not a member of this project")

        return self.send_notification(create_in, project_id=project_id)
