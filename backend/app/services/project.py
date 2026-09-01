"""Project and membership service.

Holds the project-level authorization rules that the API dependencies enforce.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, UserRole
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.project import ProjectMembershipRepository, ProjectRepository
from app.repositories.user import UserRepository
from app.schemas.project import MemberAdd, ProjectCreate, ProjectUpdate
from app.services.audit import AuditService
from app.services.auth import RequestContext

# Roles permitted to administer a project (edit it, manage its membership).
PROJECT_ADMIN_ROLES = frozenset({UserRole.PROJECT_MANAGER})


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.members = ProjectMembershipRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # --------------------------------------------------------- authorization
    def effective_role(self, project_id: uuid.UUID, user: User) -> UserRole | None:
        """The user's role on this project, or ``None`` if they have no access.

        A system ADMIN implicitly has PROJECT_MANAGER rights everywhere; that is
        the single deliberate bypass of membership. Everyone else must hold a
        membership row.
        """
        if user.role == UserRole.ADMIN:
            return UserRole.PROJECT_MANAGER
        membership = self.members.get_membership(project_id, user.id)
        return membership.role if membership else None

    def get_for_user(self, project_id: uuid.UUID, user: User) -> Project:
        """Fetch a project the user may see, else 404.

        A non-member gets 404 rather than 403: revealing that a project id
        exists is itself a leak across the tenancy boundary.
        """
        project = self.projects.get_active(project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        if self.effective_role(project_id, user) is None:
            raise NotFoundError("Project not found.")
        return project

    def require_project_admin(self, project_id: uuid.UUID, user: User) -> Project:
        project = self.get_for_user(project_id, user)
        role = self.effective_role(project_id, user)
        if role not in PROJECT_ADMIN_ROLES:
            raise PermissionDeniedError(
                "This action requires the project manager role on this project."
            )
        return project

    # ------------------------------------------------------------------ reads
    def list_for_user(
        self, user: User, *, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[Project], int]:
        if user.role == UserRole.ADMIN:
            return self.projects.list_all(skip=skip, limit=limit), self.projects.count_all()
        return (
            self.projects.list_for_user(user.id, skip=skip, limit=limit),
            self.projects.count_for_user(user.id),
        )

    def list_members(
        self, project_id: uuid.UUID, *, skip: int = 0, limit: int = 100
    ) -> tuple[Sequence[tuple[ProjectMembership, User]], int]:
        return (
            self.members.list_members(project_id, skip=skip, limit=limit),
            self.members.count_members(project_id),
        )

    # ----------------------------------------------------------------- writes
    def create(
        self, payload: ProjectCreate, actor: User, ctx: RequestContext
    ) -> Project:
        """Create a project and enrol the creator as its project manager."""
        code = payload.code.strip()
        if self.projects.get_by_code(code):
            raise ConflictError(
                f"A project with code '{code}' already exists.", code="PROJECT_CODE_TAKEN"
            )

        project = self.projects.create(
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            status=payload.status,
            client_name=payload.client_name,
            location=payload.location,
            planned_start=payload.planned_start,
            planned_finish=payload.planned_finish,
            created_by_id=actor.id,
        )
        # Without this the creator would immediately lose sight of the project.
        self.members.create(
            project_id=project.id,
            user_id=actor.id,
            role=UserRole.PROJECT_MANAGER,
        )
        self.audit.record(
            action=AuditAction.CREATE,
            entity_type="project",
            entity_id=project.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"code": project.code, "name": project.name},
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(
        self, project: Project, payload: ProjectUpdate, actor: User, ctx: RequestContext
    ) -> Project:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return project

        start = data.get("planned_start", project.planned_start)
        finish = data.get("planned_finish", project.planned_finish)
        if start and finish and finish < start:
            raise ValidationError(
                "planned_finish cannot be earlier than planned_start."
            )

        for key, value in data.items():
            setattr(project, key, value)
        self.db.add(project)
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="project",
            entity_id=project.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"fields": sorted(data)},
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def soft_delete(self, project: Project, actor: User, ctx: RequestContext) -> None:
        from datetime import UTC, datetime

        project.is_deleted = True
        project.deleted_at = datetime.now(UTC)
        self.db.add(project)
        self.audit.record(
            action=AuditAction.DELETE,
            entity_type="project",
            entity_id=project.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"soft_delete": True, "code": project.code},
        )
        self.db.commit()

    # ------------------------------------------------------------ membership
    def add_member(
        self,
        project: Project,
        payload: MemberAdd,
        actor: User,
        ctx: RequestContext,
    ) -> ProjectMembership:
        if payload.user_id is not None:
            target = self.users.get(payload.user_id)
        else:
            target = self.users.get_by_email(str(payload.email))
        if target is None or target.is_deleted:
            raise NotFoundError("User not found.")
        if not target.is_active:
            raise ValidationError(
                "Cannot add a deactivated user to a project.", code="USER_INACTIVE"
            )
        if self.members.get_membership(project.id, target.id):
            raise ConflictError(
                "This user is already a member of the project.",
                code="ALREADY_MEMBER",
            )

        membership = self.members.create(
            project_id=project.id, user_id=target.id, role=payload.role
        )
        self.audit.record(
            action=AuditAction.CREATE,
            entity_type="project_membership",
            entity_id=membership.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"user_id": str(target.id), "role": str(payload.role)},
        )
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def change_member_role(
        self,
        project: Project,
        user_id: uuid.UUID,
        new_role: UserRole,
        actor: User,
        ctx: RequestContext,
    ) -> ProjectMembership:
        membership = self.members.get_membership(project.id, user_id)
        if membership is None:
            raise NotFoundError("Membership not found.")
        if (
            membership.role == UserRole.PROJECT_MANAGER
            and new_role != UserRole.PROJECT_MANAGER
            and self.members.count_managers(project.id) <= 1
        ):
            raise ValidationError(
                "A project must retain at least one project manager.",
                code="LAST_PROJECT_MANAGER",
            )

        previous = str(membership.role)
        membership.role = new_role
        self.db.add(membership)
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="project_membership",
            entity_id=membership.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"user_id": str(user_id), "from": previous, "to": str(new_role)},
        )
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def remove_member(
        self,
        project: Project,
        user_id: uuid.UUID,
        actor: User,
        ctx: RequestContext,
    ) -> None:
        membership = self.members.get_membership(project.id, user_id)
        if membership is None:
            raise NotFoundError("Membership not found.")
        if (
            membership.role == UserRole.PROJECT_MANAGER
            and self.members.count_managers(project.id) <= 1
        ):
            raise ValidationError(
                "A project must retain at least one project manager.",
                code="LAST_PROJECT_MANAGER",
            )

        self.members.delete(membership)
        self.audit.record(
            action=AuditAction.DELETE,
            entity_type="project_membership",
            entity_id=membership.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"user_id": str(user_id)},
        )
        self.db.commit()
