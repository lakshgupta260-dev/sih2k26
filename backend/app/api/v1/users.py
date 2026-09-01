"""User administration endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import Ctx, CurrentUser, DbSession, Pagination, RequireAdmin
from app.core.exceptions import PermissionDeniedError
from app.schemas.common import Page
from app.schemas.user import (
    UserAdminCreate,
    UserRead,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=Page[UserRead],
    summary="List users (administrators only)",
)
def list_users(
    db: DbSession, _admin: RequireAdmin, page: Pagination
) -> Page[UserRead]:
    users, total = UserService(db).list(skip=page.skip, limit=page.limit)
    return Page[UserRead](
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with an explicit role (administrators only)",
)
def create_user(
    payload: UserAdminCreate, db: DbSession, admin: RequireAdmin, ctx: Ctx
) -> UserRead:
    return UserRead.model_validate(UserService(db).admin_create(payload, admin, ctx))


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Fetch a user (yourself, or any user if you are an administrator)",
)
def get_user(user_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> UserRead:
    if current_user.id != user_id and not current_user.is_admin:
        raise PermissionDeniedError("You may only view your own account.")
    return UserRead.model_validate(UserService(db).get(user_id))


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update a profile (yourself, or any user if you are an administrator)",
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> UserRead:
    if current_user.id != user_id and not current_user.is_admin:
        raise PermissionDeniedError("You may only update your own account.")
    service = UserService(db)
    target = service.get(user_id)
    return UserRead.model_validate(
        service.update_profile(target, payload, current_user, ctx)
    )


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Change a system role (administrators only)",
    description=(
        "Revokes the target user's sessions so the new role takes effect "
        "immediately rather than at token expiry."
    ),
)
def change_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: DbSession,
    admin: RequireAdmin,
    ctx: Ctx,
) -> UserRead:
    service = UserService(db)
    target = service.get(user_id)
    return UserRead.model_validate(
        service.change_role(target, payload.role, admin, ctx)
    )


@router.patch(
    "/{user_id}/status",
    response_model=UserRead,
    summary="Activate or deactivate an account (administrators only)",
)
def set_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    db: DbSession,
    admin: RequireAdmin,
    ctx: Ctx,
) -> UserRead:
    service = UserService(db)
    target = service.get(user_id)
    return UserRead.model_validate(
        service.set_active(target, payload.is_active, admin, ctx)
    )
