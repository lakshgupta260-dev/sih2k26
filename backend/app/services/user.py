"""User administration service."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, UserRole
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.user import UserAdminCreate, UserUpdate
from app.services.audit import AuditService
from app.services.auth import RequestContext


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ reads
    def get(self, user_id: uuid.UUID) -> User:
        user = self.users.get(user_id)
        if user is None or user.is_deleted:
            raise NotFoundError("User not found.")
        return user

    def list(self, *, skip: int = 0, limit: int = 50) -> tuple[Sequence[User], int]:
        return self.users.list_users(skip=skip, limit=limit), self.users.count_users()

    # ----------------------------------------------------------------- writes
    def admin_create(
        self, payload: UserAdminCreate, actor: User, ctx: RequestContext
    ) -> User:
        email = payload.email.strip().lower()
        if self.users.email_exists(email):
            raise ConflictError(
                "An account with this email already exists.", code="EMAIL_TAKEN"
            )
        user = self.users.create(
            email=email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            phone=payload.phone,
            role=payload.role,
            is_active=True,
        )
        self.audit.record(
            action=AuditAction.CREATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"created_by_admin": True, "role": str(user.role)},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_profile(
        self, user: User, payload: UserUpdate, actor: User, ctx: RequestContext
    ) -> User:
        changed: dict[str, object] = {}
        if payload.full_name is not None:
            changed["full_name"] = payload.full_name.strip()
        if payload.phone is not None:
            changed["phone"] = payload.phone
        if not changed:
            return user

        for key, value in changed.items():
            setattr(user, key, value)
        self.db.add(user)
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"fields": sorted(changed)},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def change_role(
        self, user: User, new_role: UserRole, actor: User, ctx: RequestContext
    ) -> User:
        """Change a system role.

        Two guards: an admin cannot demote themselves (which would strip the
        platform of an operator mid-session), and the last remaining admin
        cannot be demoted at all.
        """
        if user.id == actor.id and user.role == UserRole.ADMIN:
            raise ValidationError(
                "You cannot change your own admin role.", code="SELF_ROLE_CHANGE"
            )
        if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            remaining = sum(
                1
                for u in self.users.list_users(limit=1000)
                if u.role == UserRole.ADMIN and u.id != user.id and u.is_active
            )
            if remaining == 0:
                raise ValidationError(
                    "Cannot demote the last active administrator.",
                    code="LAST_ADMIN",
                )

        previous = str(user.role)
        user.role = new_role
        self.db.add(user)
        # Access tokens embed the role; force re-authentication so the change
        # takes effect immediately rather than at token expiry.
        self.tokens.revoke_all_for_user(user.id)
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"from_role": previous, "to_role": str(new_role)},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_active(
        self, user: User, is_active: bool, actor: User, ctx: RequestContext
    ) -> User:
        if user.id == actor.id and not is_active:
            raise ValidationError(
                "You cannot deactivate your own account.", code="SELF_DEACTIVATE"
            )
        user.is_active = is_active
        self.db.add(user)
        if not is_active:
            self.tokens.revoke_all_for_user(user.id)
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"is_active": is_active},
        )
        self.db.commit()
        self.db.refresh(user)
        return user
