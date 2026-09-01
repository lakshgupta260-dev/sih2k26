"""Schedules API router."""
from __future__ import annotations

import uuid
import json
from fastapi import APIRouter, status, UploadFile, File, Form, Depends

from app.api.deps import (
    Ctx,
    CurrentUser,
    DbSession,
    Pagination,
    RequireManager
)
from app.schemas.common import MessageResponse, Page
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleColumnMapping
)
from app.services.schedule import ScheduleService
from app.services.schedule_parser import ScheduleParser


router = APIRouter(prefix="/projects/{project_id}/schedules", tags=["schedules"])


@router.post(
    "",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a schedule",
    description="Upload an Excel/CSV file with a column mapping."
)
async def upload_schedule(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    mapping: str = Form(..., description="JSON string of ScheduleColumnMapping"),
) -> ScheduleRead:
    payload = ScheduleCreate(name=name, description=description)
    service = ScheduleService(db)
    
    # Creates schedule placeholder (JobStatus.PENDING)
    schedule = service.create(project_id, payload, current_user, ctx)
    
    # Parse Mapping
    mapping_data = ScheduleColumnMapping(**json.loads(mapping))
    
    # Read file
    content = await file.read()
    
    # Parse File (Synchronous for Phase 3, Phase 4 adds background jobs)
    parser = ScheduleParser(db, schedule)
    parser.parse_file(content, str(file.filename), mapping_data)
    
    # Refresh to return updated schedule with COMPLETED status
    db.refresh(schedule)
    return ScheduleRead.model_validate(schedule)


@router.get(
    "",
    response_model=Page[ScheduleRead],
    summary="List project schedules",
)
def list_schedules(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser, page: Pagination
) -> Page[ScheduleRead]:
    service = ScheduleService(db)
    schedules, total = service.list_for_project(project_id, current_user, skip=page.skip, limit=page.limit)
    items = [ScheduleRead.model_validate(s) for s in schedules]
    return Page[ScheduleRead](
        items=items, total=total, skip=page.skip, limit=page.limit
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleRead,
    summary="Get schedule details",
)
def get_schedule(
    project_id: uuid.UUID, schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ScheduleRead:
    service = ScheduleService(db)
    schedule = service.get_for_user(schedule_id, current_user)
    return ScheduleRead.model_validate(schedule)

