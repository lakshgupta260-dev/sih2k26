from datetime import date
from typing import Annotated
import uuid

from pydantic import BaseModel, ConfigDict, Field
from app.core.constants import ActivityStatus

class ActualProgressCreate(BaseModel):
    reporting_date: date
    actual_quantity: float | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    status: ActivityStatus = ActivityStatus.NOT_STARTED
    notes: str | None = None

class ActualProgressRead(ActualProgressCreate):
    id: uuid.UUID
    activity_id: uuid.UUID
    reported_by_id: uuid.UUID | None
    
    model_config = ConfigDict(from_attributes=True)

class ActivityProgressRollup(BaseModel):
    activity_id: uuid.UUID
    activity_code: str
    name: str
    wbs_path: str
    level: int
    completion_percentage: float
    status: ActivityStatus
    is_delayed: bool
