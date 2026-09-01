"""Authentication endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import Ctx, CurrentUser, DbSession
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse
from app.schemas.user import PasswordChange, UserCreate, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description=(
        "Self-registration. The new account always receives the "
        "SITE_SUPERVISOR role; only an administrator can grant a higher one."
    ),
)
def register(payload: UserCreate, db: DbSession, ctx: Ctx) -> UserRead:
    user = AuthService(db).register(payload, ctx)
    return UserRead.model_validate(user)


@router.post("/login", response_model=LoginResponse, summary="Log in")
def login(payload: LoginRequest, db: DbSession, ctx: Ctx) -> LoginResponse:
    user, pair = AuthService(db).login(payload.email, payload.password, ctx)
    return LoginResponse(
        **pair.model_dump(), user=UserRead.model_validate(user)
    )


@router.post(
    "/token",
    response_model=TokenPair,
    summary="Log in (OAuth2 form)",
    description=(
        "Form-encoded variant of /auth/login, present so the Swagger "
        "**Authorize** button works. Send the email address in the `username` "
        "field. Application clients should use /auth/login."
    ),
)
def login_form(
    db: DbSession,
    ctx: Ctx,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPair:
    _, pair = AuthService(db).login(form.username, form.password, ctx)
    return pair


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token for a new token pair",
    description=(
        "Refresh tokens are rotated: the presented token is revoked and a new "
        "one issued. Replaying a revoked token revokes every session for that "
        "user, on the assumption it was stolen."
    ),
)
def refresh(payload: RefreshRequest, db: DbSession, ctx: Ctx) -> TokenPair:
    return AuthService(db).refresh(payload.refresh_token, ctx)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke one session, or all of them",
)
def logout(
    payload: LogoutRequest,
    db: DbSession,
    ctx: Ctx,
    current_user: CurrentUser,
) -> MessageResponse:
    revoked = AuthService(db).logout(current_user, payload.refresh_token, ctx)
    return MessageResponse(message=f"Revoked {revoked} session(s).")


@router.get("/me", response_model=UserRead, summary="The authenticated user")
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change your password",
    description="All other sessions are revoked on success.",
)
def change_password(
    payload: PasswordChange,
    db: DbSession,
    ctx: Ctx,
    current_user: CurrentUser,
) -> MessageResponse:
    AuthService(db).change_password(
        current_user, payload.current_password, payload.password, ctx
    )
    return MessageResponse(message="Password changed. Please sign in again.")
