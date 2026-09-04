"""User and refresh-token models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import UserRole
from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project, ProjectMembership


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An authenticated principal.

    ``role`` is the *system-wide* role. A user may additionally hold a
    different, narrower role on an individual project -- see
    :class:`~app.models.project.ProjectMembership`.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_normalised: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)

    role: Mapped[UserRole] = mapped_column(
        String(32), nullable=False, default=UserRole.SITE_SUPERVISOR, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_projects: Mapped[list["Project"]] = relationship(
        back_populates="created_by", foreign_keys="Project.created_by_id"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A server-side record of an issued refresh token.

    JWTs are stateless, so "log out" is meaningless unless the server keeps a
    revocation record. Storing the ``jti`` (not the token itself) lets a refresh
    token be invalidated without ever persisting a usable credential.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),
    )

    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def is_usable(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(tz=self.expires_at.tzinfo)
        return self.revoked_at is None and self.expires_at > now
