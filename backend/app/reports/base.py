"""Base abstract class for document report builders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseReportBuilder(ABC):
    """Abstract interface for snapshot-based report builders."""

    def __init__(self, project_name: str, parameters: dict[str, Any] | None = None) -> None:
        self.project_name = project_name
        self.parameters = parameters or {}

    @abstractmethod
    def build(self, data: dict[str, Any]) -> bytes:
        """Render report payload into binary bytes (PDF/XLSX)."""
        pass
