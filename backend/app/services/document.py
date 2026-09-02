"""Validates uploads, creates durable jobs, and enforces project isolation."""
from __future__ import annotations
import hashlib, io, uuid, zipfile
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger
from app.core.constants import AuditAction, DocumentType, JobStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.models.document import ProcessingJob, ProgressReport, UploadedFile
from app.models.user import User
from app.repositories.document import ProcessingJobRepository, ProgressReportRepository, UploadedFileRepository
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.project import ProjectService

logger = get_logger(__name__)


class UploadValidator:
    types = {".pdf": {"application/pdf"}, ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}, ".xls": {"application/vnd.ms-excel"}, ".csv": {"text/csv", "application/csv"}, ".txt": {"text/plain"}, ".xml": {"application/xml", "text/xml"}, ".png": {"image/png"}, ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}}
    @staticmethod
    def validate(filename: str | None, content_type: str | None, content: bytes) -> tuple[str, str]:
        name, suffix = Path(filename or "").name, Path(filename or "").suffix.lower()
        if not name or not suffix: raise ValidationError("A filename with an extension is required.", code="INVALID_FILENAME")
        if suffix not in {x.lower() for x in settings.ALLOWED_UPLOAD_EXTENSIONS}: raise ValidationError("This file extension is not allowed.", code="UNSUPPORTED_FILE_TYPE")
        if not content: raise ValidationError("Uploaded files cannot be empty.", code="EMPTY_FILE")
        if len(content) > settings.max_upload_bytes: raise ValidationError(f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.", code="FILE_TOO_LARGE")
        declared = (content_type or "application/octet-stream").split(";", 1)[0].lower()
        if suffix in UploadValidator.types and declared not in UploadValidator.types[suffix] | {"application/octet-stream"}: raise ValidationError("Content type does not match the file extension.", code="CONTENT_TYPE_MISMATCH")
        if suffix == ".pdf" and not content.startswith(b"%PDF-"): raise ValidationError("File content is not a PDF.", code="MAGIC_BYTES_MISMATCH")
        if suffix == ".xlsx":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive: names = set(archive.namelist())
                if "[Content_Types].xml" not in names or not any(x.startswith("xl/") for x in names): raise ValueError
            except (ValueError, zipfile.BadZipFile) as exc: raise ValidationError("File content is not an XLSX workbook.", code="MAGIC_BYTES_MISMATCH") from exc
        return name, declared

class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db, self.files, self.jobs, self.reports = db, UploadedFileRepository(db), ProcessingJobRepository(db), ProgressReportRepository(db)
        self.projects, self.audit = ProjectService(db), AuditService(db)
    def upload(self, project_id: uuid.UUID, actor: User, ctx: RequestContext, *, filename: str | None, content_type: str | None, content: bytes, document_type: DocumentType) -> tuple[UploadedFile, ProcessingJob]:
        self.projects.get_for_user(project_id, actor); name, mime = UploadValidator.validate(filename, content_type, content)
        relative = Path(str(project_id)) / f"{uuid.uuid4().hex}{Path(name).suffix.lower()}"; root = Path(settings.UPLOAD_DIR).resolve(); target = (root / relative).resolve()
        try: target.relative_to((root / str(project_id)).resolve())
        except ValueError as exc: raise ValidationError("Invalid upload storage path.", code="INVALID_STORAGE_PATH") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(content)
            uploaded = self.files.create(project_id=project_id, uploaded_by_id=actor.id, original_filename=name, storage_path=relative.as_posix(), content_type=mime, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), document_type=document_type)
            job = self.jobs.create(project_id=project_id, uploaded_file_id=uploaded.id)
            self.audit.record(action=AuditAction.UPLOAD, entity_type="uploaded_file", entity_id=uploaded.id, actor_user_id=actor.id, project_id=project_id, ip_address=ctx.ip_address, user_agent=ctx.user_agent, details={"filename": name, "size_bytes": len(content)})
            self.db.commit(); self.db.refresh(uploaded); self.db.refresh(job)
        except Exception:
            self.db.rollback(); target.unlink(missing_ok=True); raise
        # Queueing is a separate transaction: the file and its job row are
        # already committed, so a broker outage must not lose them.
        try:
            from app.tasks.document_tasks import process_uploaded_file
            job.celery_task_id = process_uploaded_file.delay(str(job.id)).id
            self.db.commit(); self.db.refresh(job)
        except Exception as exc:  # noqa: BLE001 - broker reachability is not ours
            # Swallowing this silently left the job PENDING with no task id and
            # nothing that would ever pick it up, so a client polling
            # /jobs/{id} waited forever on a job that did not exist anywhere.
            # Marking it FAILED with the reason makes the outage visible and
            # the job re-runnable.
            self.db.rollback()
            logger.error("document_job_not_queued", extra={"job_id": str(job.id), "error": str(exc)})
            try:
                job.status = JobStatus.FAILED
                job.error_message = f"Could not queue processing: {exc}"[:4000]
                self.db.commit(); self.db.refresh(job)
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.exception("document_job_status_not_recorded", extra={"job_id": str(job.id)})
        return uploaded, job
    def get_job(self, job_id: uuid.UUID, actor: User) -> ProcessingJob:
        job = self.jobs.get(job_id)
        if job is None: raise NotFoundError("Processing job not found.")
        self.projects.get_for_user(job.project_id, actor); return job
    def list_files(self, project_id: uuid.UUID, actor: User, *, skip: int, limit: int) -> tuple[list[UploadedFile], int]:
        self.projects.get_for_user(project_id, actor); return list(self.files.list_for_project(project_id, skip=skip, limit=limit)), self.files.count_for_project(project_id)
    def get_file(self, project_id: uuid.UUID, file_id: uuid.UUID, actor: User) -> UploadedFile:
        self.projects.get_for_user(project_id, actor); item = self.files.get(file_id)
        if item is None or item.project_id != project_id: raise NotFoundError("Uploaded file not found.")
        return item
    def list_reports(self, project_id: uuid.UUID, actor: User, *, skip: int, limit: int) -> tuple[list[ProgressReport], int]:
        self.projects.get_for_user(project_id, actor); return list(self.reports.list_for_project(project_id, skip=skip, limit=limit)), self.reports.count_for_project(project_id)
    def get_report(self, project_id: uuid.UUID, report_id: uuid.UUID, actor: User) -> ProgressReport:
        self.projects.get_for_user(project_id, actor); report = self.reports.get(report_id)
        if report is None or report.project_id != project_id: raise NotFoundError("Progress report not found.")
        return report
