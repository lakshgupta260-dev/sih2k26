"""Unit tests for NotificationService and channel dispatchers."""
from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from app.core.constants import NotificationChannel, NotificationStatus
from app.schemas.reporting import NotificationCreate
from app.services.notification import NotificationService


def test_notification_service_dispatches_in_app_notification(db: Session, make_user) -> None:
    user = make_user()
    service = NotificationService(db)

    create_in = NotificationCreate(
        channel=NotificationChannel.IN_APP,
        recipient_user_id=user.id,
        notification_type="delay_alert",
        title="Delay Warning",
        body="Activity A101 is delayed by 5 days.",
    )

    notification = service.send_notification(create_in)
    assert notification.status == NotificationStatus.DELIVERED
    assert notification.provider_message_id is not None
    assert notification.provider_message_id.startswith("in_app_")


def test_notification_idempotency_prevents_duplicate_dispatch(db: Session, make_user) -> None:
    user = make_user()
    service = NotificationService(db)
    key = f"idempotent-{uuid.uuid4().hex}"

    create_in = NotificationCreate(
        channel=NotificationChannel.IN_APP,
        recipient_user_id=user.id,
        notification_type="system_alert",
        idempotency_key=key,
        title="System Notice",
        body="Server reboot scheduled.",
    )

    first = service.send_notification(create_in)
    second = service.send_notification(create_in)

    assert first.id == second.id


def test_notification_read_unread_flow(db: Session, make_user) -> None:
    user = make_user()
    service = NotificationService(db)

    for i in range(3):
        service.send_notification(
            NotificationCreate(
                channel=NotificationChannel.IN_APP,
                recipient_user_id=user.id,
                notification_type="test_event",
                title=f"Title {i}",
                body=f"Body {i}",
            )
        )

    assert service.get_unread_count(user.id) == 3

    items, total = service.list_user_notifications(user.id, unread_only=True)
    assert total == 3
    assert len(items) == 3

    # Mark one as read
    first_id = items[0].id
    service.mark_as_read(first_id, user.id)
    assert service.get_unread_count(user.id) == 2

    # Mark all remaining as read
    service.mark_all_as_read(user.id)
    assert service.get_unread_count(user.id) == 0
