"""User and refresh-token persistence."""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session) -> None:
        super().__init__(User, db)

    def get_by_email(self, email: str) -> User | None:
        """Case-insensitive lookup; emails are stored lowercased on write."""
        stmt = select(User).where(User.email == email.strip().lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id, User.is_active.is_(True), User.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def list_users(
        self, *, skip: int = 0, limit: int = 50, include_deleted: bool = False
    ) -> Sequence[User]:
        stmt = select(User)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted.is_(False))
        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def count_users(self, *, include_deleted: bool = False) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(User)
        if not include_deleted:
            stmt = stmt.where(User.is_deleted.is_(False))
        return int(self.db.execute(stmt).scalar_one())

    def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        self.db.add(user)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, db: Session) -> None:
        super().__init__(RefreshToken, db)

    def get_by_jti(self, jti: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        return self.db.execute(stmt).scalar_one_or_none()

    def revoke(self, token: RefreshToken) -> None:
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            self.db.add(token)

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every live session. Used for logout-everywhere and on
        role/status changes, where stale tokens would otherwise keep old
        privileges alive until they expire."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return int(self.db.execute(stmt).rowcount or 0)
