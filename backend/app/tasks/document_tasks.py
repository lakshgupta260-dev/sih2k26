"""Celery task producing a normalized report from one stored upload.

The job row is claimed under a row lock before any work starts. Celery
redelivers tasks -- on ``acks_late``, on a visibility timeout, on a manual
retry -- and without a claim two workers process the same upload concurrently.
The second one then trips the unique constraint on
``progress_reports.uploaded_file_id`` and marks the job ``FAILED`` *after* the
first worker already marked it ``COMPLETED``, so the API reports a failure for
a document that was processed fine.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.constants import JobStatus
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.document_processing import processor_for
from app.models.document import ProcessingJob, ProgressReport
from app.worker import celery_app

logger = get_logger(__name__)

# States a job may be picked up from. COMPLETED is done; PROCESSING means
# another worker holds it.
_CLAIMABLE = (JobStatus.PENDING, JobStatus.FAILED)


@celery_app.task(name="documents.process_uploaded_file")
def process_uploaded_file(job_id: str) -> None:
    db = SessionLocal()
    job = None
    try:
        # SELECT ... FOR UPDATE, so a concurrent delivery of the same job
        # blocks here and then sees the state this worker committed.
        job = db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.id == uuid.UUID(job_id))
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            logger.warning("document_processing_unknown_job", extra={"job_id": job_id})
            return
        if job.status not in _CLAIMABLE:
            logger.info(
                "document_processing_skipped",
                extra={"job_id": job_id, "status": str(job.status)},
            )
            db.rollback()
            return

        # Claim it and release the lock, so the row is visibly PROCESSING while
        # the parse runs rather than holding a transaction open for minutes.
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(UTC)
        # A retry after a failure must not keep the previous attempt's error or
        # completion timestamp.
        job.error_message = None
        job.completed_at = None
        db.commit()

        source = (
            Path(settings.UPLOAD_DIR).resolve() / job.uploaded_file.storage_path
        ).resolve()
        if not source.is_file():
            raise FileNotFoundError("Stored upload no longer exists.")
        project_root = (
            Path(settings.UPLOAD_DIR).resolve() / str(job.project_id)
        ).resolve()
        source.relative_to(project_root)

        processor = processor_for(source)
        result = processor.process(source)

        existing = db.execute(
            select(ProgressReport).where(
                ProgressReport.uploaded_file_id == job.uploaded_file_id
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ProgressReport(
                    project_id=job.project_id,
                    uploaded_file_id=job.uploaded_file_id,
                    raw_text=result.raw_text,
                    extracted_data=result.metadata,
                )
            )
        else:
            # A retry of a job whose report already landed refreshes it rather
            # than failing on the unique constraint.
            existing.raw_text = result.raw_text
            existing.extracted_data = result.metadata

        job.processor = processor.name
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        db.commit()

    except Exception as exc:  # noqa: BLE001 - a worker must not die on one job
        db.rollback()
        if job is not None:
            try:
                # Re-read under a lock: another worker may have completed it
                # while this one was failing, and overwriting a COMPLETED job
                # with FAILED would report a success as a failure.
                current = db.execute(
                    select(ProcessingJob)
                    .where(ProcessingJob.id == job.id)
                    .with_for_update()
                ).scalar_one_or_none()
                if current is not None and current.status != JobStatus.COMPLETED:
                    current.status = JobStatus.FAILED
                    current.error_message = str(exc)[:4000]
                    current.completed_at = datetime.now(UTC)
                    db.commit()
                else:
                    db.rollback()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception(
                    "document_processing_status_not_recorded",
                    extra={"job_id": job_id},
                )
        logger.exception("document_processing_failed", extra={"job_id": job_id})
    finally:
        db.close()
