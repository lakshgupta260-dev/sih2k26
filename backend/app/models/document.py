"""Uploaded-source, background-processing and normalized-report models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import Discipline, DocumentType, JobStatus
from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class UploadedFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "uploaded_files"
    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(String(40), nullable=False, default=DocumentType.OTHER)
    project: Mapped["Project"] = relationship()
    uploaded_by: Mapped["User | None"] = relationship()
    processing_job: Mapped["ProcessingJob | None"] = relationship(back_populates="uploaded_file", uselist=False)
    progress_report: Mapped["ProgressReport | None"] = relationship(back_populates="uploaded_file", uselist=False)


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_file_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    status: Mapped[JobStatus] = mapped_column(String(32), nullable=False, default=JobStatus.PENDING, index=True)
    processor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped["Project"] = relationship()
    uploaded_file: Mapped["UploadedFile"] = relationship(back_populates="processing_job")


class ProgressReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "progress_reports"
    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_file_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    discipline: Mapped[Discipline | None] = mapped_column(String(50), nullable=True, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    project: Mapped["Project"] = relationship()
    uploaded_file: Mapped["UploadedFile"] = relationship(back_populates="progress_report")
