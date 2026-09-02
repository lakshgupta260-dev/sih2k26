"""Schedules API router."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import (
    AccessibleProject,
    Ctx,
    CurrentUser,
    DbSession,
    ManagedProject,
    Pagination,
)
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.schemas.common import Page
from app.schemas.schedule import ScheduleColumnMapping, ScheduleCreate, ScheduleRead
from app.services.schedule import ScheduleService
from app.services.schedule_parser import ScheduleParser

router = APIRouter(prefix="/projects/{project_id}/schedules", tags=["schedules"])

# The extensions this endpoint can actually parse. Narrower than the global
# upload allowlist, which also covers PDFs and images destined for the document
# pipeline -- accepting one of those here would create a schedule row and then
# fail on read.
_SCHEDULE_EXTENSIONS = (".csv", ".xls", ".xlsx", ".xlsm")


def _parse_mapping(raw: str) -> ScheduleColumnMapping:
    """Validate the column mapping before anything is written.

    This runs before the schedule row is created, deliberately. Creating the
    row first and parsing the mapping afterwards turned a malformed mapping
    into an unhandled 500 *and* left a schedule stuck in PENDING forever, since
    the code path that marks a schedule FAILED lives inside the parser and was
    never reached.
    """
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"The mapping field is not valid JSON: {exc.msg}.",
            code="INVALID_COLUMN_MAPPING",
        ) from exc
    if not isinstance(decoded, dict):
        raise ValidationError(
            "The mapping field must be a JSON object of "
            "our-field-name -> your-column-name.",
            code="INVALID_COLUMN_MAPPING",
        )
    try:
        return ScheduleColumnMapping(**decoded)
    except Exception as exc:  # noqa: BLE001 - pydantic's own error, reshaped
        raise ValidationError(
            f"The mapping field is not a valid column mapping: {exc}",
            code="INVALID_COLUMN_MAPPING",
        ) from exc


def _validate_upload(filename: str | None, content: bytes) -> None:
    """Reject what this endpoint cannot parse, before it reaches the parser."""
    name = (filename or "").strip()
    if not name:
        raise ValidationError("A filename is required.", code="MISSING_FILENAME")
    if not name.lower().endswith(_SCHEDULE_EXTENSIONS):
        raise ValidationError(
            "A schedule must be a "
            f"{', '.join(_SCHEDULE_EXTENSIONS)} file, got '{name}'.",
            code="UNSUPPORTED_SCHEDULE_FORMAT",
        )
    if not content:
        raise ValidationError("The uploaded file is empty.", code="EMPTY_UPLOAD")
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > limit:
        raise ValidationError(
            f"The file is {len(content) / 1024 / 1024:.1f} MB, over the "
            f"{settings.MAX_UPLOAD_SIZE_MB} MB limit.",
            code="UPLOAD_TOO_LARGE",
            details={"size_bytes": len(content), "limit_bytes": limit},
        )


@router.post(
    "",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a baseline schedule",
    description=(
        "Upload an Excel/CSV schedule with a column mapping. The mapping and "
        "the file are both validated before anything is written, so a bad "
        "request never leaves a half-created schedule behind.\n\n"
        "The response carries `parse_summary`: rows read, activities created, "
        "and every row, date and dependency the parser could not use. A "
        "schedule can import successfully and still have dropped edges — the "
        "summary is where that shows up.\n\n"
        "Requires the project manager role."
    ),
)
async def upload_schedule(
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    mapping: str = Form(..., description="JSON string of ScheduleColumnMapping"),
) -> ScheduleRead:
    mapping_data = _parse_mapping(mapping)
    content = await file.read()
    _validate_upload(file.filename, content)

    payload = ScheduleCreate(name=name, description=description)
    service = ScheduleService(db)
    schedule = service.create(project.id, payload, current_user, ctx)

    # Synchronous for Phase 3; the document pipeline's job machinery is the
    # model to follow when this moves to a worker.
    ScheduleParser(db, schedule).parse_file(content, str(file.filename), mapping_data)

    db.refresh(schedule)
    return ScheduleRead.model_validate(schedule)


@router.get(
    "",
    response_model=Page[ScheduleRead],
    summary="List project schedules",
)
def list_schedules(
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination,
) -> Page[ScheduleRead]:
    service = ScheduleService(db)
    schedules, total = service.list_for_project(
        project.id, current_user, skip=page.skip, limit=page.limit
    )
    return Page[ScheduleRead](
        items=[ScheduleRead.model_validate(s) for s in schedules],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleRead,
    summary="Get schedule details",
    description=(
        "The schedule must belong to the project in the path; a schedule id "
        "from elsewhere is a 404 even when the caller can see both projects."
    ),
)
def get_schedule(
    schedule_id: uuid.UUID,
    project: AccessibleProject,
    db: DbSession,
    current_user: CurrentUser,
) -> ScheduleRead:
    service = ScheduleService(db)
    schedule = service.get_for_user(schedule_id, current_user, project_id=project.id)
    return ScheduleRead.model_validate(schedule)
