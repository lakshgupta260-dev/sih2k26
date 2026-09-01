"""Tenant-isolated source-document and job-polling APIs."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, File, Form, UploadFile, status
from app.api.deps import Ctx, CurrentUser, DbSession, Pagination
from app.core.constants import DocumentType
from app.schemas.common import Page
from app.schemas.document import ProcessingJobRead, UploadAccepted, UploadedFileRead
from app.services.document import DocumentService
router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])
jobs_router = APIRouter(prefix="/jobs", tags=["processing jobs"])
@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser, ctx: Ctx, file: UploadFile = File(...), document_type: DocumentType = Form(DocumentType.OTHER)) -> UploadAccepted:
    uploaded, job = DocumentService(db).upload(project_id, current_user, ctx, filename=file.filename, content_type=file.content_type, content=await file.read(), document_type=document_type)
    return UploadAccepted(file=UploadedFileRead.model_validate(uploaded), job=ProcessingJobRead.model_validate(job))
@router.get("", response_model=Page[UploadedFileRead])
def list_documents(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser, page: Pagination) -> Page[UploadedFileRead]:
    items, total = DocumentService(db).list_files(project_id, current_user, skip=page.skip, limit=page.limit); return Page(items=[UploadedFileRead.model_validate(x) for x in items], total=total, skip=page.skip, limit=page.limit)
@router.get("/{file_id}", response_model=UploadedFileRead)
def get_document(project_id: uuid.UUID, file_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> UploadedFileRead:
    return UploadedFileRead.model_validate(DocumentService(db).get_file(project_id, file_id, current_user))
@jobs_router.get("/{job_id}", response_model=ProcessingJobRead)
def get_processing_job(job_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ProcessingJobRead:
    return ProcessingJobRead.model_validate(DocumentService(db).get_job(job_id, current_user))
