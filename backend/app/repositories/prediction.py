"""Data access for the model registry and stored predictions."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.prediction import DelayModelVersion, DelayPrediction


class DelayModelVersionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def active_for_project(self, project_id: uuid.UUID) -> DelayModelVersion | None:
        """The model currently served for a project.

        A project-scoped model wins over a global one: a model fitted on this
        project's own history is the better predictor of it, even if a global
        model saw more rows.
        """
        scoped = self.db.execute(
            select(DelayModelVersion)
            .where(
                DelayModelVersion.project_id == project_id,
                DelayModelVersion.is_active.is_(True),
            )
            .order_by(DelayModelVersion.created_at.desc())
        ).scalars().first()
        if scoped is not None:
            return scoped
        return self.db.execute(
            select(DelayModelVersion)
            .where(
                DelayModelVersion.project_id.is_(None),
                DelayModelVersion.is_active.is_(True),
            )
            .order_by(DelayModelVersion.created_at.desc())
        ).scalars().first()

    def list_for_project(
        self, project_id: uuid.UUID, *, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[DelayModelVersion], int]:
        condition = (
            (DelayModelVersion.project_id == project_id)
            | (DelayModelVersion.project_id.is_(None))
        )
        total = self.db.execute(
            select(func.count()).select_from(DelayModelVersion).where(condition)
        ).scalar_one()
        rows = self.db.execute(
            select(DelayModelVersion)
            .where(condition)
            .order_by(DelayModelVersion.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
        return rows, total

    def deactivate_for_project(self, project_id: uuid.UUID | None) -> None:
        """Retire the previous model for a scope.

        Rows are kept rather than deleted so an older prediction still points
        at the artefact that produced it.
        """
        condition = (
            DelayModelVersion.project_id.is_(None)
            if project_id is None
            else DelayModelVersion.project_id == project_id
        )
        for row in self.db.execute(
            select(DelayModelVersion).where(condition, DelayModelVersion.is_active.is_(True))
        ).scalars():
            row.is_active = False

    def create(self, **kwargs) -> DelayModelVersion:
        row = DelayModelVersion(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row


class DelayPredictionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def by_activity(self, activity_id: uuid.UUID) -> DelayPrediction | None:
        return self.db.execute(
            select(DelayPrediction).where(DelayPrediction.activity_id == activity_id)
        ).scalar_one_or_none()

    def existing_for_schedule(
        self, schedule_id: uuid.UUID
    ) -> dict[uuid.UUID, DelayPrediction]:
        rows = self.db.execute(
            select(DelayPrediction).where(DelayPrediction.schedule_id == schedule_id)
        ).scalars()
        return {row.activity_id: row for row in rows}

    def list_for_schedule(
        self,
        schedule_id: uuid.UUID,
        *,
        risk_level: str | None = None,
        predicted_late: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[DelayPrediction], int]:
        stmt = select(DelayPrediction).where(DelayPrediction.schedule_id == schedule_id)
        count_stmt = (
            select(func.count())
            .select_from(DelayPrediction)
            .where(DelayPrediction.schedule_id == schedule_id)
        )
        if risk_level is not None:
            stmt = stmt.where(DelayPrediction.risk_level == risk_level)
            count_stmt = count_stmt.where(DelayPrediction.risk_level == risk_level)
        if predicted_late is not None:
            stmt = stmt.where(DelayPrediction.predicted_late.is_(predicted_late))
            count_stmt = count_stmt.where(
                DelayPrediction.predicted_late.is_(predicted_late)
            )

        total = self.db.execute(count_stmt).scalar_one()
        rows = self.db.execute(
            stmt.order_by(DelayPrediction.probability.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
        return rows, total

    def risk_counts(self, schedule_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(DelayPrediction.risk_level, func.count())
            .where(DelayPrediction.schedule_id == schedule_id)
            .group_by(DelayPrediction.risk_level)
        ).all()
        return {level: count for level, count in rows}

    def worst_slip(self, schedule_id: uuid.UUID) -> int | None:
        return self.db.execute(
            select(func.max(DelayPrediction.forecast_slip_days)).where(
                DelayPrediction.schedule_id == schedule_id
            )
        ).scalar_one_or_none()
