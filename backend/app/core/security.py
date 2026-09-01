"""Password hashing and JSON Web Token primitives.

This module is deliberately free of database and FastAPI imports: it deals in
strings and claims only. That keeps it unit-testable and means the token format
can change without touching the service layer.

Two token types are issued, distinguished by the ``type`` claim so an access
token can never be replayed as a refresh token:

* **access**  — short-lived, sent on every request.
* **refresh** — long-lived, single-purpose, and carries a ``jti`` that is
  recorded in the database so it can actually be revoked on logout.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Final, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh"]

ACCESS_TOKEN: Final[TokenType] = "access"
REFRESH_TOKEN: Final[TokenType] = "refresh"

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)

# bcrypt silently truncates input beyond 72 bytes, which would make two long
# passwords sharing a prefix equivalent. Reject rather than truncate.
BCRYPT_MAX_BYTES: Final[int] = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password exceeds {BCRYPT_MAX_BYTES} bytes once UTF-8 encoded."
        )
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification. Never raises on a malformed hash."""
    if len(plain.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001 - a corrupt hash must read as "no match"
        return False


@lru_cache(maxsize=1)
def _timing_dummy_hash() -> str:
    """A real bcrypt hash of a throwaway value.

    Computed once, on first use, so the import stays fast. Used to equalise the
    cost of a login attempt for an address that has no account -- see
    :func:`dummy_verify`.
    """
    return _pwd_context.hash("not-a-real-password-timing-equalisation-only")


def dummy_verify(password: str) -> None:
    """Burn one bcrypt verification and discard the result.

    Called when no user matches the supplied email, so that "no such account"
    and "wrong password" take comparable time and the login endpoint cannot be
    used to discover which addresses are registered.
    """
    verify_password(password, _timing_dummy_hash())


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Encode a JWT. Returns ``(token, jti, expires_at)``."""
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti, expires_at


def create_access_token(
    subject: str, extra_claims: dict[str, Any] | None = None
) -> tuple[str, str, datetime]:
    return _create_token(
        subject,
        ACCESS_TOKEN,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str) -> tuple[str, str, datetime]:
    return _create_token(
        subject,
        REFRESH_TOKEN,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises :class:`AuthenticationError` for anything wrong -- expiry, bad
    signature, wrong token type -- so callers never have to distinguish, and
    the API never leaks *why* a token failed.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid.", code="TOKEN_INVALID") from exc

    if payload.get("type") != expected_type:
        raise AuthenticationError(
            "Token is not valid for this operation.", code="TOKEN_WRONG_TYPE"
        )
    return payload
