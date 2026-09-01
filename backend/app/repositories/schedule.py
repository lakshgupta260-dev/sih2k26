"""Schedule and Activity repositories."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schedule import Schedule, Activity, ActivityDependency
from app.repositories.base import BaseRepository


class ScheduleRepository(BaseRepository[Schedule]):
    def __init__(self, db: Session) -> None:
        super().__init__(Schedule, db)

    def list_for_project(
        self, project_id: uuid.UUID, *, skip: int = 0, limit: int = 50
    ) -> Sequence[Schedule]:
        stmt = (
            select(Schedule)
            .filter_by(project_id=project_id, is_deleted=False)
            .order_by(Schedule.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def count_for_project(self, project_id: uuid.UUID) -> int:
        return self.count(project_id=project_id, is_deleted=False)


class ActivityRepository(BaseRepository[Activity]):
    def __init__(self, db: Session) -> None:
        super().__init__(Activity, db)

    def list_by_schedule(
        self, schedule_id: uuid.UUID, *, skip: int = 0, limit: int = 100
    ) -> Sequence[Activity]:
        stmt = (
            select(Activity)
            .filter_by(schedule_id=schedule_id)
            .order_by(Activity.wbs_path)
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()


class ActivityDependencyRepository(BaseRepository[ActivityDependency]):
    def __init__(self, db: Session) -> None:
        super().__init__(ActivityDependency, db)
