"""Authentication service: registration, login, refresh, logout.

Owns the transaction boundary for every auth operation and is the only place
that turns credentials into tokens.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuditAction, UserRole
from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate
from app.services.audit import AuditService

logger = get_logger(__name__)


class RequestContext:
    """The bits of the HTTP request that belong in the audit trail."""

    __slots__ = ("ip_address", "user_agent")

    def __init__(self, ip_address: str | None = None, user_agent: str | None = None):
        self.ip_address = ip_address
        self.user_agent = user_agent


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)
        self.audit = AuditService(db)

    # --------------------------------------------------------------- register
    def register(
        self, payload: UserCreate, ctx: RequestContext | None = None
    ) -> User:
        """Create a self-registered user.

        The role is always SITE_SUPERVISOR — privilege escalation is an
        administrative action, never something a registrant can request.
        """
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
            role=UserRole.SITE_SUPERVISOR,
            is_active=True,
        )
        ctx = ctx or RequestContext()
        self.audit.record(
            action=AuditAction.CREATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"self_registered": True, "role": str(user.role)},
        )
        self.db.commit()
        self.db.refresh(user)
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return user

    # ------------------------------------------------------------------ login
    def authenticate(self, email: str, password: str) -> User:
        """Verify credentials.

        The same error is returned for "no such user", "wrong password" and
        "deactivated account" so the endpoint cannot be used to enumerate who
        holds an account. A dummy hash comparison runs when the user is absent
        to keep response timing roughly constant.
        """
        user = self.users.get_by_email(email)
        if user is None:
            dummy_verify(password)  # equalise response timing
            raise AuthenticationError("Incorrect email or password.")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active or user.is_deleted:
            raise AuthenticationError("Incorrect email or password.")
        return user

    def login(
        self, email: str, password: str, ctx: RequestContext | None = None
    ) -> tuple[User, TokenPair]:
        user = self.authenticate(email, password)
        ctx = ctx or RequestContext()
        pair = self._issue_tokens(user, ctx)
        self.users.touch_last_login(user)
        self.audit.record(
            action=AuditAction.LOGIN,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        self.db.commit()
        self.db.refresh(user)
        return user, pair

    # ---------------------------------------------------------------- refresh
    def refresh(self, refresh_token: str, ctx: RequestContext | None = None) -> TokenPair:
        """Exchange a refresh token for a new pair, rotating the refresh token.

        Rotation means a stolen refresh token is usable at most once before the
        legitimate client's next refresh invalidates it.
        """
        payload = decode_token(refresh_token, "refresh")
        stored = self.tokens.get_by_jti(payload["jti"])

        if stored is None:
            raise AuthenticationError("Token is invalid.", code="TOKEN_INVALID")
        if stored.revoked_at is not None:
            # A revoked token being replayed suggests theft; drop every session.
            self.tokens.revoke_all_for_user(stored.user_id)
            self.db.commit()
            logger.warning(
                "refresh_token_reuse_detected",
                extra={"user_id": str(stored.user_id)},
            )
            raise AuthenticationError("Token is invalid.", code="TOKEN_REVOKED")
        if stored.expires_at <= datetime.now(UTC):
            raise AuthenticationError("Token has expired.", code="TOKEN_EXPIRED")

        user = self.users.get_active(stored.user_id)
        if user is None:
            raise AuthenticationError("Token is invalid.", code="TOKEN_INVALID")

        self.tokens.revoke(stored)
        ctx = ctx or RequestContext()
        pair = self._issue_tokens(user, ctx)
        self.db.commit()
        return pair

    # ----------------------------------------------------------------- logout
    def logout(
        self,
        user: User,
        refresh_token: str | None,
        ctx: RequestContext | None = None,
    ) -> int:
        """Revoke one session, or all of them when no token is supplied."""
        revoked = 0
        if refresh_token:
            try:
                payload = decode_token(refresh_token, "refresh")
            except AuthenticationError:
                payload = None
            if payload:
                stored = self.tokens.get_by_jti(payload["jti"])
                # Never let one user revoke another user's session.
                if stored is not None and stored.user_id == user.id:
                    self.tokens.revoke(stored)
                    revoked = 1
        else:
            revoked = self.tokens.revoke_all_for_user(user.id)

        ctx = ctx or RequestContext()
        self.audit.record(
            action=AuditAction.LOGOUT,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"sessions_revoked": revoked},
        )
        self.db.commit()
        return revoked

    # -------------------------------------------------------- change password
    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        ctx: RequestContext | None = None,
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise ValidationError(
                "Current password is incorrect.", code="INVALID_CURRENT_PASSWORD"
            )
        user.hashed_password = hash_password(new_password)
        self.db.add(user)
        # Every other session is now stale; force re-authentication.
        self.tokens.revoke_all_for_user(user.id)
        ctx = ctx or RequestContext()
        self.audit.record(
            action=AuditAction.UPDATE,
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={"password_changed": True},
        )
        self.db.commit()

    # ---------------------------------------------------------------- helpers
    def _issue_tokens(self, user: User, ctx: RequestContext) -> TokenPair:
        access, _, _ = create_access_token(
            str(user.id), extra_claims={"role": str(user.role), "email": user.email}
        )
        refresh, jti, expires_at = create_refresh_token(str(user.id))
        self.tokens.create(
            jti=jti,
            user_id=user.id,
            expires_at=expires_at,
            user_agent=(ctx.user_agent or "")[:400] or None,
            ip_address=ctx.ip_address,
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def resolve_access_token(self, token: str) -> User:
        """Turn a bearer access token into a live, active user."""
        payload = decode_token(token, "access")
        try:
            user_id = uuid.UUID(payload["sub"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthenticationError("Token is invalid.", code="TOKEN_INVALID") from exc

        user = self.users.get_active(user_id)
        if user is None:
            raise AuthenticationError(
                "User account is inactive or no longer exists.",
                code="USER_INACTIVE",
            )
        return user
