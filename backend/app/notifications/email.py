"""Email notification channel dispatcher."""
from __future__ import annotations

import logging
import uuid
from app.models.reporting import Notification
from app.notifications.base import BaseChannelDispatcher, DispatchResult

logger = logging.getLogger(__name__)


class EmailDispatcher(BaseChannelDispatcher):
    """Email notification channel with dry-run/logging support."""

    def dispatch(self, notification: Notification) -> DispatchResult:
        recipient = notification.recipient_address
        if not recipient and notification.recipient_user:
            recipient = notification.recipient_user.email

        if not recipient:
            return DispatchResult(
                success=False,
                error_message="No recipient email address provided",
            )

        logger.info(
            "Sending Email notification to %s: [%s] %s",
            recipient,
            notification.title,
            notification.body,
        )
        msg_id = f"email_msg_{uuid.uuid4().hex[:12]}"
        return DispatchResult(success=True, provider_message_id=msg_id)
