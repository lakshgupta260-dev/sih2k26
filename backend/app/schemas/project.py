"""Project and membership contracts."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.constants import ProjectStatus, UserRole
from app.schemas.common import ORMModel


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    client_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    planned_start: date | None = None
    planned_finish: date | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "ProjectBase":
        if (
            self.planned_start
            and self.planned_finish
            and self.planned_finish < self.planned_start
        ):
            raise ValueError("planned_finish cannot be earlier than planned_start.")
        return self


class ProjectCreate(ProjectBase):
    code: str = Field(
        min_length=2,
        max_length=50,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Short unique identifier, e.g. PROJ-OIL-PL02.",
    )
    status: ProjectStatus = ProjectStatus.PLANNING


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: ProjectStatus | None = None
    client_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    planned_start: date | None = None
    planned_finish: date | None = None


class ProjectRead(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: ProjectStatus
    client_name: str | None
    location: str | None
    planned_start: date | None
    planned_finish: date | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectWithRole(ProjectRead):
    """A project plus the requesting user's effective role on it."""

    my_role: UserRole


class MemberAdd(BaseModel):
    """Add a member by user id or by email — whichever the caller has."""

    user_id: uuid.UUID | None = None
    email: EmailStr | None = None
    role: UserRole = UserRole.SITE_SUPERVISOR

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "MemberAdd":
        if (self.user_id is None) == (self.email is None):
            raise ValueError("Provide exactly one of user_id or email.")
        return self


class MemberRoleUpdate(BaseModel):
    role: UserRole


class MemberRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: UserRole
    created_at: datetime


class MemberDetail(MemberRead):
    email: str
    full_name: str
    is_active: bool
