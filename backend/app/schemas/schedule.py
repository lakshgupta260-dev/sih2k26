"""Schedule and Activity contracts."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.constants import JobStatus, WBSLevel, Discipline, DependencyType
from app.schemas.common import ORMModel


class ScheduleBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    uploaded_by_id: uuid.UUID | None
    status: JobStatus
    created_at: datetime
    updated_at: datetime


class ActivityDependencyRead(ORMModel):
    id: uuid.UUID
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dependency_type: DependencyType
    lag: float


class ActivityRead(ORMModel):
    id: uuid.UUID
    schedule_id: uuid.UUID
    activity_code: str
    name: str
    wbs_path: str
    level: int
    discipline: Discipline | None
    planned_start: date | None
    planned_finish: date | None
    budgeted_quantity: float | None
    uom: str | None
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ActivityWithDependencies(ActivityRead):
    predecessors: list[ActivityDependencyRead] = []
    successors: list[ActivityDependencyRead] = []


class ScheduleColumnMapping(BaseModel):
    """Client-provided mapping from their file's columns to our schema fields."""
    activity_code: str
    name: str
    wbs_path: str | None = None
    level: str | None = None
    discipline: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    budgeted_quantity: str | None = None
    uom: str | None = None
    
    # If a dependency is provided inline (e.g. Primavera exported CSV)
    predecessors: str | None = None


class ActivityTreeNode(ActivityRead):
    children: list["ActivityTreeNode"] = []

