"""Persisted project report artefacts and channel-specific notifications."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    GeneratedReportFormat,
    GeneratedReportStatus,
    NotificationChannel,
    NotificationStatus,
)
from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class GeneratedReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable, private report artefact generated for one project.

    ``storage_path`` is deliberately an internal object-store key, never a
    public URL. The eventual download service authorizes project access before
    streaming this object, so a copied database value cannot grant access.
    """

    __tablename__ = "generated_reports"
    __table_args__ = (
        Index("ix_generated_reports_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    output_format: Mapped[GeneratedReportFormat] = mapped_column(
        String(16), nullable=False, index=True
    )
    status: Mapped[GeneratedReportStatus] = mapped_column(
        String(32), nullable=False, default=GeneratedReportStatus.PENDING, index=True
    )

    # Persist the request/snapshot context: regenerated reports must not be
    # mistaken for the artifact a user downloaded at an earlier point in time.
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship()
    requested_by: Mapped["User | None"] = relationship()


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One channel-specific delivery attempt for an application event.

    A service may create several rows with the same ``event_key`` to fan one
    event out to multiple channels. Keeping delivery state per channel avoids
    an email failure obscuring an already-delivered in-app notification.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "channel != 'IN_APP' OR recipient_user_id IS NOT NULL",
            name="in_app_requires_user",
        ),
        Index("ix_notifications_recipient_status_created", "recipient_user_id", "status", "created_at"),
        Index("ix_notifications_project_created", "project_id", "created_at"),
    )

    # ``project_id`` is optional for account-level notifications such as a
    # password-reset email. Project notifications remain tenant-scoped.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        String(32), nullable=False, default=NotificationStatus.PENDING, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    # Address is a delivery endpoint (email address, phone number, etc.), not
    # an authorization primitive; the service resolves and validates it.
    recipient_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project | None"] = relationship()
    recipient_user: Mapped["User | None"] = relationship()
