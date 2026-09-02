"""Base channel dispatcher interface for notifications."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.models.reporting import Notification


@dataclass
class DispatchResult:
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None


class BaseChannelDispatcher(ABC):
    """Abstract interface for channel-specific notification delivery."""

    @abstractmethod
    def dispatch(self, notification: Notification) -> DispatchResult:
        """Deliver notification to the target channel."""
        pass
