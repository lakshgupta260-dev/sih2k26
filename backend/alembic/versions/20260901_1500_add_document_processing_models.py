"""Add document uploads, jobs and parsed reports.

Revision ID: f4a1e8c9b2d3
Revises: d93681770df1
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a1e8c9b2d3"
down_revision: str | None = "d93681770df1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table("uploaded_files", sa.Column("project_id", sa.UUID(), nullable=False), sa.Column("uploaded_by_id", sa.UUID(), nullable=True), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("storage_path", sa.String(500), nullable=False), sa.Column("content_type", sa.String(150), nullable=False), sa.Column("size_bytes", sa.BigInteger(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("document_type", sa.String(40), nullable=False), sa.Column("id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("storage_path"))
    op.create_index("ix_uploaded_files_project_id", "uploaded_files", ["project_id"]); op.create_index("ix_uploaded_files_sha256", "uploaded_files", ["sha256"])
    op.create_table("processing_jobs", sa.Column("project_id", sa.UUID(), nullable=False), sa.Column("uploaded_file_id", sa.UUID(), nullable=False), sa.Column("celery_task_id", sa.String(100), nullable=True), sa.Column("status", sa.String(32), nullable=False), sa.Column("processor", sa.String(100), nullable=True), sa.Column("error_message", sa.Text(), nullable=True), sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_processing_jobs_project_id", "processing_jobs", ["project_id"]); op.create_index("ix_processing_jobs_uploaded_file_id", "processing_jobs", ["uploaded_file_id"], unique=True); op.create_index("ix_processing_jobs_celery_task_id", "processing_jobs", ["celery_task_id"], unique=True); op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_table("progress_reports", sa.Column("project_id", sa.UUID(), nullable=False), sa.Column("uploaded_file_id", sa.UUID(), nullable=False), sa.Column("report_date", sa.Date(), nullable=True), sa.Column("discipline", sa.String(50), nullable=True), sa.Column("raw_text", sa.Text(), nullable=False), sa.Column("extracted_data", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False), sa.Column("id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_progress_reports_project_id", "progress_reports", ["project_id"]); op.create_index("ix_progress_reports_uploaded_file_id", "progress_reports", ["uploaded_file_id"], unique=True); op.create_index("ix_progress_reports_report_date", "progress_reports", ["report_date"]); op.create_index("ix_progress_reports_discipline", "progress_reports", ["discipline"])

def downgrade() -> None:
    op.drop_table("progress_reports"); op.drop_table("processing_jobs"); op.drop_table("uploaded_files")
