"""Add generated report artefacts and channel-specific notifications (Phase 8).

Generated reports retain a private storage key plus the request and data
snapshot that produced the file. Notifications store one row per delivery
channel, allowing the notification service to fan an event out without mixing
the status of an in-app delivery with an email or future provider delivery.

Revision ID: 6c4ed7f85001
Revises: 533f361c3eaa
Create Date: 2026-09-02 15:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6c4ed7f85001"
down_revision: str | None = "533f361c3eaa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_reports",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("output_format", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_generated_reports_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], name=op.f("fk_generated_reports_requested_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_reports")),
        sa.UniqueConstraint("storage_path", name=op.f("uq_generated_reports_storage_path")),
    )
    op.create_index(op.f("ix_generated_reports_project_id"), "generated_reports", ["project_id"], unique=False)
    op.create_index(op.f("ix_generated_reports_requested_by_id"), "generated_reports", ["requested_by_id"], unique=False)
    op.create_index(op.f("ix_generated_reports_report_type"), "generated_reports", ["report_type"], unique=False)
    op.create_index(op.f("ix_generated_reports_output_format"), "generated_reports", ["output_format"], unique=False)
    op.create_index(op.f("ix_generated_reports_status"), "generated_reports", ["status"], unique=False)
    op.create_index(op.f("ix_generated_reports_sha256"), "generated_reports", ["sha256"], unique=False)
    op.create_index("ix_generated_reports_project_created", "generated_reports", ["project_id", "created_at"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("recipient_user_id", sa.UUID(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("recipient_address", sa.String(length=320), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_notifications_attempt_count_nonnegative")),
        sa.CheckConstraint("channel != 'IN_APP' OR recipient_user_id IS NOT NULL", name=op.f("ck_notifications_in_app_requires_user")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_notifications_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], name=op.f("fk_notifications_recipient_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_notifications_idempotency_key")),
    )
    for column in ("project_id", "recipient_user_id", "channel", "status", "notification_type", "event_key", "provider_message_id", "scheduled_for"):
        op.create_index(op.f(f"ix_notifications_{column}"), "notifications", [column], unique=False)
    op.create_index("ix_notifications_recipient_status_created", "notifications", ["recipient_user_id", "status", "created_at"], unique=False)
    op.create_index("ix_notifications_project_created", "notifications", ["project_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_project_created", table_name="notifications")
    op.drop_index("ix_notifications_recipient_status_created", table_name="notifications")
    for column in ("scheduled_for", "provider_message_id", "event_key", "notification_type", "status", "channel", "recipient_user_id", "project_id"):
        op.drop_index(op.f(f"ix_notifications_{column}"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_generated_reports_project_created", table_name="generated_reports")
    for column in ("sha256", "status", "output_format", "report_type", "requested_by_id", "project_id"):
        op.drop_index(op.f(f"ix_generated_reports_{column}"), table_name="generated_reports")
    op.drop_table("generated_reports")
