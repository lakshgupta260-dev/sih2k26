"""Notification dispatch package."""
from app.notifications.base import BaseChannelDispatcher, DispatchResult
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.email import EmailDispatcher
from app.notifications.in_app import InAppDispatcher
from app.notifications.whatsapp import WhatsAppDispatcher

__all__ = [
    "BaseChannelDispatcher",
    "DispatchResult",
    "NotificationDispatcher",
    "InAppDispatcher",
    "EmailDispatcher",
    "WhatsAppDispatcher",
]
