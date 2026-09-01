"""User request/response contracts."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import UserRole
from app.schemas.common import ORMModel

PASSWORD_MIN = 8
PASSWORD_MAX = 72  # bcrypt truncates beyond 72 bytes


class PasswordMixin(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if len(v.encode("utf-8")) > PASSWORD_MAX:
            raise ValueError("Password is too long once UTF-8 encoded.")
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters and at least one number.")
        return v


class UserCreate(PasswordMixin):
    """Public self-registration payload.

    Note there is no ``role`` field: registration always produces a
    SITE_SUPERVISOR. Elevation is an administrative action, never self-service.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class UserAdminCreate(UserCreate):
    """Administrator-created user, where the role may be chosen."""

    role: UserRole = UserRole.SITE_SUPERVISOR


class UserUpdate(BaseModel):
    """Self-service profile edit. Deliberately cannot change role or status."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    is_active: bool


class PasswordChange(PasswordMixin):
    current_password: str


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
