"""Project and membership persistence."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, db: Session) -> None:
        super().__init__(Project, db)

    def get_active(self, project_id: uuid.UUID) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id, Project.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Project | None:
        stmt = select(Project).where(Project.code == code.strip())
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self, *, skip: int = 0, limit: int = 50) -> Sequence[Project]:
        stmt = (
            select(Project)
            .where(Project.is_deleted.is_(False))
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def count_all(self) -> int:
        stmt = select(func.count()).select_from(Project).where(
            Project.is_deleted.is_(False)
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_for_user(
        self, user_id: uuid.UUID, *, skip: int = 0, limit: int = 50
    ) -> Sequence[Project]:
        """Only projects the user is actually a member of."""
        stmt = (
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                ProjectMembership.user_id == user_id,
                Project.is_deleted.is_(False),
            )
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def count_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                ProjectMembership.user_id == user_id,
                Project.is_deleted.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one())


class ProjectMembershipRepository(BaseRepository[ProjectMembership]):
    def __init__(self, db: Session) -> None:
        super().__init__(ProjectMembership, db)

    def get_membership(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> ProjectMembership | None:
        stmt = select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_members(
        self, project_id: uuid.UUID, *, skip: int = 0, limit: int = 100
    ) -> Sequence[tuple[ProjectMembership, User]]:
        stmt = (
            select(ProjectMembership, User)
            .join(User, User.id == ProjectMembership.user_id)
            .where(ProjectMembership.project_id == project_id)
            .order_by(User.full_name)
            .offset(skip)
            .limit(limit)
        )
        return [(m, u) for m, u in self.db.execute(stmt).all()]

    def count_members(self, project_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(ProjectMembership)
            .where(ProjectMembership.project_id == project_id)
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_managers(self, project_id: uuid.UUID) -> int:
        from app.core.constants import UserRole

        stmt = (
            select(func.count())
            .select_from(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.role == UserRole.PROJECT_MANAGER,
            )
        )
        return int(self.db.execute(stmt).scalar_one())
