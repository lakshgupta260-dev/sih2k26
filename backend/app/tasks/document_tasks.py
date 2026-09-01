"""Celery task producing a normalized report from one stored upload."""
from __future__ import annotations
import uuid
from datetime import UTC, datetime
from pathlib import Path
from app.core.config import settings
from app.core.constants import JobStatus
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.document_processing import processor_for
from app.models.document import ProcessingJob, ProgressReport
from app.worker import celery_app
logger = get_logger(__name__)
@celery_app.task(name="documents.process_uploaded_file")
def process_uploaded_file(job_id: str) -> None:
    db = SessionLocal(); job = None
    try:
        job = db.get(ProcessingJob, uuid.UUID(job_id))
        if job is None or job.status == JobStatus.COMPLETED: return
        source = (Path(settings.UPLOAD_DIR).resolve() / job.uploaded_file.storage_path).resolve()
        if not source.is_file(): raise FileNotFoundError("Stored upload no longer exists.")
        project_root = (Path(settings.UPLOAD_DIR).resolve() / str(job.project_id)).resolve()
        source.relative_to(project_root)
        job.status, job.started_at, job.error_message = JobStatus.PROCESSING, datetime.now(UTC), None; db.commit()
        processor = processor_for(source); result = processor.process(source)
        if db.query(ProgressReport).filter_by(uploaded_file_id=job.uploaded_file_id).one_or_none() is None:
            db.add(ProgressReport(project_id=job.project_id, uploaded_file_id=job.uploaded_file_id, raw_text=result.raw_text, extracted_data=result.metadata))
        job.processor, job.status, job.completed_at = processor.name, JobStatus.COMPLETED, datetime.now(UTC); db.commit()
    except Exception as exc:
        db.rollback()
        if job is not None:
            job.status, job.error_message, job.completed_at = JobStatus.FAILED, str(exc)[:4000], datetime.now(UTC); db.commit()
        logger.exception("document_processing_failed", extra={"job_id": job_id})
    finally: db.close()
