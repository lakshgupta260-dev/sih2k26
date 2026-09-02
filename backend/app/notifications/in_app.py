"""In-App notification channel dispatcher."""
from __future__ import annotations

import uuid
from app.models.reporting import Notification
from app.notifications.base import BaseChannelDispatcher, DispatchResult


class InAppDispatcher(BaseChannelDispatcher):
    """In-app notification channel.

    In-app notifications are stored directly in the database notifications table
    and made queryable via the recipient user inbox API.
    """

    def dispatch(self, notification: Notification) -> DispatchResult:
        if not notification.recipient_user_id:
            return DispatchResult(
                success=False,
                error_message="recipient_user_id is required for IN_APP channel",
            )
        msg_id = f"in_app_{uuid.uuid4().hex[:12]}"
        return DispatchResult(success=True, provider_message_id=msg_id)
