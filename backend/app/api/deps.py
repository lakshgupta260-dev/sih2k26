"""Shared FastAPI dependencies: sessions, authentication and authorization.

Routers import their guards from here so authorization is declared in one
place. A route with no guard is unauthenticated by construction, which makes
the access rules auditable by reading the router signatures.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.common import PaginationParams
from app.services.auth import AuthService, RequestContext
from app.services.project import ProjectService

DbSession = Annotated[Session, Depends(get_db)]

# auto_error=False so a missing header produces our error envelope rather than
# FastAPI's bare {"detail": ...}.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def pagination_params(skip: int = 0, limit: int = 50) -> PaginationParams:
    """Validated offset/limit, shared by every collection endpoint."""
    return PaginationParams(skip=skip, limit=limit)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]


def get_request_context(request: Request) -> RequestContext:
    """Client metadata for the audit trail."""
    client_host = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_host = forwarded.split(",")[0].strip()
    return RequestContext(
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
    )


Ctx = Annotated[RequestContext, Depends(get_request_context)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    """Resolve the bearer access token to an active user, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required.", code="NOT_AUTHENTICATED")
    return AuthService(db).resolve_access_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: UserRole) -> Callable[[User], User]:
    """Dependency factory gating a route on the caller's *system* role.

    Project-scoped permissions are a separate concern -- see
    :func:`get_project_for_user` and :func:`require_project_admin`.
    """
    allowed_set = frozenset(allowed)

    def _guard(current_user: CurrentUser) -> User:
        if current_user.role not in allowed_set:
            raise PermissionDeniedError(
                "Your role does not permit this action.",
                details={
                    "required_roles": sorted(str(r) for r in allowed_set),
                    "your_role": str(current_user.role),
                },
            )
        return current_user

    return _guard


RequireAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
RequireManager = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.PROJECT_MANAGER))
]


def get_project_for_user(
    db: DbSession,
    current_user: CurrentUser,
    project_id: Annotated[uuid.UUID, Path(description="Project id")],
) -> Project:
    """Load a project the caller is allowed to see, else 404."""
    return ProjectService(db).get_for_user(project_id, current_user)


AccessibleProject = Annotated[Project, Depends(get_project_for_user)]


def require_project_admin(
    db: DbSession,
    current_user: CurrentUser,
    project_id: Annotated[uuid.UUID, Path(description="Project id")],
) -> Project:
    """Load a project the caller may administer, else 404/403."""
    return ProjectService(db).require_project_admin(project_id, current_user)


ManagedProject = Annotated[Project, Depends(require_project_admin)]
