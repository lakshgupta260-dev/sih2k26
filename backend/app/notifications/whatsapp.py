"""WhatsApp notification channel dispatcher."""
from __future__ import annotations

import logging
import uuid
import httpx
from app.models.reporting import Notification
from app.notifications.base import BaseChannelDispatcher, DispatchResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class WhatsAppDispatcher(BaseChannelDispatcher):
    """WhatsApp outbound channel using Meta Cloud API with dry-run/logging fallback."""

    def dispatch(self, notification: Notification) -> DispatchResult:
        recipient = notification.recipient_address
        if not recipient:
            return DispatchResult(
                success=False,
                error_message="No recipient phone number provided for WHATSAPP channel",
            )

        # Meta API Config
        access_token = settings.META_ACCESS_TOKEN
        phone_id = settings.META_PHONE_NUMBER_ID

        if not access_token or not phone_id:
            logger.info(
                "[DRY RUN] Sending WhatsApp notification to %s: %s",
                recipient,
                notification.body,
            )
            msg_id = f"wa_msg_{uuid.uuid4().hex[:12]}"
            return DispatchResult(success=True, provider_message_id=msg_id)

        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": notification.body
            }
        }

        try:
            # We use a synchronous httpx Client because dispatch is called synchronously
            # from Celery tasks or API threads.
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Meta returns a messages array with the created id
                messages = data.get("messages", [])
                if messages and "id" in messages[0]:
                    msg_id = messages[0]["id"]
                else:
                    msg_id = f"wa_msg_{uuid.uuid4().hex[:12]}"
                    
                return DispatchResult(success=True, provider_message_id=msg_id)
        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            logger.error("WhatsApp API error: %s - %s", e.response.status_code, error_details)
            return DispatchResult(
                success=False,
                error_message=f"WhatsApp API HTTP {e.response.status_code}: {error_details}"
            )
        except Exception as e:
            logger.exception("Failed to send WhatsApp message")
            return DispatchResult(
                success=False,
                error_message=str(e)
            )
