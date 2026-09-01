"""Schedule business logic and authorization."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, JobStatus
from app.core.exceptions import NotFoundError
from app.models.schedule import Schedule, Activity
from app.models.user import User
from app.repositories.schedule import ScheduleRepository, ActivityRepository, ActivityDependencyRepository
from app.schemas.schedule import ScheduleCreate
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.project import ProjectService


class ScheduleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.schedules = ScheduleRepository(db)
        self.activities = ActivityRepository(db)
        self.dependencies = ActivityDependencyRepository(db)
        self.projects = ProjectService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------- schedules
    def get_for_user(self, schedule_id: uuid.UUID, user: User) -> Schedule:
        schedule = self.schedules.get_by(id=schedule_id, is_deleted=False)
        if schedule is None:
            raise NotFoundError("Schedule not found.")
        # Ensure user can see the project
        self.projects.get_for_user(schedule.project_id, user)
        return schedule

    def list_for_project(
        self, project_id: uuid.UUID, user: User, *, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[Schedule], int]:
        # Ensure user can see the project
        self.projects.get_for_user(project_id, user)
        return (
            self.schedules.list_for_project(project_id, skip=skip, limit=limit),
            self.schedules.count_for_project(project_id),
        )

    def create(
        self, project_id: uuid.UUID, payload: ScheduleCreate, actor: User, ctx: RequestContext
    ) -> Schedule:
        # Require project admin or write access (using project manager for now, following Phase 2 pattern)
        self.projects.require_project_admin(project_id, actor)

        schedule = self.schedules.create(
            project_id=project_id,
            name=payload.name.strip(),
            description=payload.description,
            uploaded_by_id=actor.id,
            status=JobStatus.PENDING
        )
        self.audit.record(
            action=AuditAction.UPLOAD,
            entity_type="schedule",
            entity_id=schedule.id,
            actor_user_id=actor.id,
            project_id=project_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"name": schedule.name},
        )
        self.db.commit()
        self.db.refresh(schedule)
        return schedule
    
    # ------------------------------------------------------------- activities
    def get_activity_for_user(self, activity_id: uuid.UUID, user: User) -> Activity:
        activity = self.activities.get(activity_id)
        if activity is None:
            raise NotFoundError("Activity not found.")
        # Ensure user can see the schedule/project
        self.get_for_user(activity.schedule_id, user)
        return activity

    def list_activities(
        self, schedule_id: uuid.UUID, user: User, *, skip: int = 0, limit: int = 100
    ) -> tuple[Sequence[Activity], int]:
        self.get_for_user(schedule_id, user)
        return (
            self.activities.list_by_schedule(schedule_id, skip=skip, limit=limit),
            self.activities.count(schedule_id=schedule_id),
        )
