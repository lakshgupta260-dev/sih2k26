"""Multi-channel notification dispatcher registry."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.constants import NotificationChannel, NotificationStatus
from app.models.reporting import Notification
from app.notifications.base import BaseChannelDispatcher
from app.notifications.email import EmailDispatcher
from app.notifications.in_app import InAppDispatcher
from app.notifications.whatsapp import WhatsAppDispatcher


class NotificationDispatcher:
    """Registry and executor for channel dispatchers."""

    def __init__(self) -> None:
        self._dispatchers: dict[NotificationChannel, BaseChannelDispatcher] = {
            NotificationChannel.IN_APP: InAppDispatcher(),
            NotificationChannel.EMAIL: EmailDispatcher(),
            NotificationChannel.WHATSAPP: WhatsAppDispatcher(),
        }

    def dispatch(self, notification: Notification) -> None:
        dispatcher = self._dispatchers.get(notification.channel)
        notification.attempt_count += 1

        if not dispatcher:
            notification.status = NotificationStatus.FAILED
            notification.last_error = f"Unsupported channel: {notification.channel}"
            return

        result = dispatcher.dispatch(notification)
        if result.success:
            notification.status = NotificationStatus.DELIVERED
            notification.provider_message_id = result.provider_message_id
            notification.sent_at = datetime.now(timezone.utc)
            notification.delivered_at = datetime.now(timezone.utc)
            notification.last_error = None
        else:
            notification.status = NotificationStatus.FAILED
            notification.last_error = result.error_message
