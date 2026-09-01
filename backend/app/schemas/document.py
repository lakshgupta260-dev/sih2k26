"""Public contracts for uploads, jobs and parsed reports."""
from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import Any
from pydantic import Field
from app.core.constants import Discipline, DocumentType, JobStatus
from app.schemas.common import ORMModel

class UploadedFileRead(ORMModel):
    id: uuid.UUID; project_id: uuid.UUID; uploaded_by_id: uuid.UUID | None
    original_filename: str; content_type: str; size_bytes: int; sha256: str; document_type: DocumentType
    created_at: datetime; updated_at: datetime
class ProcessingJobRead(ORMModel):
    id: uuid.UUID; project_id: uuid.UUID; uploaded_file_id: uuid.UUID; status: JobStatus
    processor: str | None; error_message: str | None; started_at: datetime | None; completed_at: datetime | None
    created_at: datetime; updated_at: datetime
class UploadAccepted(ORMModel):
    file: UploadedFileRead; job: ProcessingJobRead
class ProgressReportRead(ORMModel):
    id: uuid.UUID; project_id: uuid.UUID; uploaded_file_id: uuid.UUID
    report_date: date | None; discipline: Discipline | None; raw_text: str
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime; updated_at: datetime
