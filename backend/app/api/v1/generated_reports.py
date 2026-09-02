"""APIs for generating and downloading project report artifacts."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Response, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.reporting import GeneratedReportCreate, GeneratedReportRead
from app.services.reporting import ReportService

router = APIRouter(prefix="/projects/{project_id}/generated-reports", tags=["generated reports"])


@router.post("", response_model=GeneratedReportRead, status_code=status.HTTP_201_CREATED)
def request_report(
    project_id: uuid.UUID,
    body: GeneratedReportCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> GeneratedReportRead:
    report = ReportService(db).generate_report(
        project_id=project_id,
        report_type=body.report_type,
        output_format=body.output_format,
        parameters=body.parameters,
        current_user=current_user,
    )
    return GeneratedReportRead.model_validate(report)


@router.get("", response_model=Page[GeneratedReportRead])
def list_generated_reports(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination,
) -> Page[GeneratedReportRead]:
    items, total = ReportService(db).list_reports(
        project_id, current_user, skip=page.skip, limit=page.limit
    )
    return Page(
        items=[GeneratedReportRead.model_validate(x) for x in items],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )


@router.get("/{report_id}", response_model=GeneratedReportRead)
def get_generated_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> GeneratedReportRead:
    report = ReportService(db).get_report(project_id, report_id, current_user)
    return GeneratedReportRead.model_validate(report)


@router.get("/{report_id}/download")
def download_generated_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    file_path, filename, content_type = ReportService(db).get_report_file_path(
        project_id, report_id, current_user
    )
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=content_type,
    )
