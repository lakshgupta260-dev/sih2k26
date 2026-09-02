"""WhatsApp notification channel dispatcher."""
from __future__ import annotations

import logging
import uuid
from app.models.reporting import Notification
from app.notifications.base import BaseChannelDispatcher, DispatchResult

logger = logging.getLogger(__name__)


class WhatsAppDispatcher(BaseChannelDispatcher):
    """WhatsApp outbound channel with dry-run/logging support."""

    def dispatch(self, notification: Notification) -> DispatchResult:
        recipient = notification.recipient_address
        if not recipient:
            return DispatchResult(
                success=False,
                error_message="No recipient phone number provided for WHATSAPP channel",
            )

        logger.info(
            "Sending WhatsApp notification to %s: %s",
            recipient,
            notification.body,
        )
        msg_id = f"wa_msg_{uuid.uuid4().hex[:12]}"
        return DispatchResult(success=True, provider_message_id=msg_id)
