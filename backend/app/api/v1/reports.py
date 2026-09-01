"""Read-only APIs for normalized reports created by document jobs."""
from __future__ import annotations
import uuid
from fastapi import APIRouter
from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.document import ProgressReportRead
from app.services.document import DocumentService
router = APIRouter(prefix="/projects/{project_id}/reports", tags=["progress reports"])
@router.get("", response_model=Page[ProgressReportRead])
def list_reports(project_id: uuid.UUID, db: DbSession, current_user: CurrentUser, page: Pagination) -> Page[ProgressReportRead]:
    items, total = DocumentService(db).list_reports(project_id, current_user, skip=page.skip, limit=page.limit); return Page(items=[ProgressReportRead.model_validate(x) for x in items], total=total, skip=page.skip, limit=page.limit)
@router.get("/{report_id}", response_model=ProgressReportRead)
def get_report(project_id: uuid.UUID, report_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ProgressReportRead:
    return ProgressReportRead.model_validate(DocumentService(db).get_report(project_id, report_id, current_user))
