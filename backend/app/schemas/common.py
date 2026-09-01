"""Schemas shared by every router."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class ORMModel(BaseModel):
    """Base for schemas read directly off SQLAlchemy instances."""

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """The single error envelope returned by every failing endpoint."""

    error: ErrorDetail


class Page(BaseModel, Generic[ItemT]):
    """Offset-paginated collection response."""

    items: list[ItemT]
    total: int
    skip: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.skip + len(self.items) < self.total


class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    checks_passed: bool


class MessageResponse(BaseModel):
    message: str
