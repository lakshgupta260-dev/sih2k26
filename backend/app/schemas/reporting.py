"""Public contracts for generated project reports and notifications."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.constants import (
    GeneratedReportFormat,
    GeneratedReportStatus,
    NotificationChannel,
    NotificationStatus,
)
from app.schemas.common import ORMModel


class GeneratedReportCreate(BaseModel):
    """A request to generate a project report from data as of a given date."""

    report_type: str = Field(min_length=1, max_length=64)
    output_format: GeneratedReportFormat
    as_of: date | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class GeneratedReportRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    requested_by_id: uuid.UUID | None
    report_type: str
    output_format: GeneratedReportFormat
    status: GeneratedReportStatus
    parameters: dict[str, Any]
    snapshot: dict[str, Any]
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    error_message: str | None
    generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationCreate(BaseModel):
    """Service input for a single delivery channel, not a public send API."""

    project_id: uuid.UUID | None = None
    recipient_user_id: uuid.UUID | None = None
    channel: NotificationChannel
    notification_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    recipient_address: str | None = Field(None, max_length=320)
    event_key: str | None = Field(None, max_length=128)
    idempotency_key: str | None = Field(None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    scheduled_for: datetime | None = None

    @model_validator(mode="after")
    def validate_recipient(self) -> "NotificationCreate":
        if self.channel == NotificationChannel.IN_APP and self.recipient_user_id is None:
            raise ValueError("recipient_user_id is required for in-app notifications")
        return self


class NotificationRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    recipient_user_id: uuid.UUID | None
    channel: NotificationChannel
    status: NotificationStatus
    notification_type: str
    event_key: str | None
    title: str
    body: str
    payload: dict[str, Any]
    attempt_count: int
    last_error: str | None
    scheduled_for: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationMarkRead(BaseModel):
    """Empty body used by the future in-app read acknowledgement endpoint."""

