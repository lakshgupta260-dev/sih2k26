"""Project and membership endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    AccessibleProject,
    Ctx,
    CurrentUser,
    DbSession,
    ManagedProject,
    Pagination,
    RequireManager,
    bearer_scheme,
)
from app.schemas.common import MessageResponse, Page
from app.schemas.project import (
    MemberAdd,
    MemberDetail,
    MemberRead,
    MemberRoleUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectWithRole,
)
from app.services.project import ProjectService

# Project routes are authenticated. Declaring the bearer dependency here also
# publishes the security requirement to OpenAPI, so Swagger UI attaches the
# authorized token to manager-only routes such as project creation.
router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(bearer_scheme)],
)


@router.get(
    "",
    response_model=Page[ProjectWithRole],
    summary="List projects visible to you",
    description=(
        "Administrators see every project. Everyone else sees only the "
        "projects they are a member of."
    ),
)
def list_projects(
    db: DbSession, current_user: CurrentUser, page: Pagination
) -> Page[ProjectWithRole]:
    service = ProjectService(db)
    projects, total = service.list_for_user(
        current_user, skip=page.skip, limit=page.limit
    )
    items = [
        ProjectWithRole(
            **ProjectRead.model_validate(p).model_dump(),
            my_role=service.effective_role(p.id, current_user),
        )
        for p in projects
    ]
    return Page[ProjectWithRole](
        items=items, total=total, skip=page.skip, limit=page.limit
    )


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description=(
        "Requires ADMIN or PROJECT_MANAGER. The creator is enrolled "
        "automatically as project manager."
    ),
)
def create_project(
    payload: ProjectCreate, db: DbSession, actor: RequireManager, ctx: Ctx
) -> ProjectRead:
    return ProjectRead.model_validate(ProjectService(db).create(payload, actor, ctx))


@router.get("/{project_id}", response_model=ProjectWithRole, summary="Fetch a project")
def get_project(
    project: AccessibleProject, db: DbSession, current_user: CurrentUser
) -> ProjectWithRole:
    service = ProjectService(db)
    return ProjectWithRole(
        **ProjectRead.model_validate(project).model_dump(),
        my_role=service.effective_role(project.id, current_user),
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (project managers and administrators)",
)
def update_project(
    payload: ProjectUpdate,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> ProjectRead:
    return ProjectRead.model_validate(
        ProjectService(db).update(project, payload, current_user, ctx)
    )


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    summary="Soft-delete a project (project managers and administrators)",
)
def delete_project(
    project: ManagedProject, db: DbSession, current_user: CurrentUser, ctx: Ctx
) -> MessageResponse:
    ProjectService(db).soft_delete(project, current_user, ctx)
    return MessageResponse(message="Project deleted.")


# ------------------------------------------------------------------ members
@router.get(
    "/{project_id}/members",
    response_model=Page[MemberDetail],
    summary="List project members",
)
def list_members(
    project: AccessibleProject, db: DbSession, page: Pagination
) -> Page[MemberDetail]:
    rows, total = ProjectService(db).list_members(
        project.id, skip=page.skip, limit=page.limit
    )
    items = [
        MemberDetail(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            role=m.role,
            created_at=m.created_at,
            email=u.email,
            full_name=u.full_name,
            is_active=u.is_active,
        )
        for m, u in rows
    ]
    return Page[MemberDetail](
        items=items, total=total, skip=page.skip, limit=page.limit
    )


@router.post(
    "/{project_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member (project managers and administrators)",
)
def add_member(
    payload: MemberAdd,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> MemberRead:
    return MemberRead.model_validate(
        ProjectService(db).add_member(project, payload, current_user, ctx)
    )


@router.patch(
    "/{project_id}/members/{user_id}",
    response_model=MemberRead,
    summary="Change a member's project role",
)
def change_member_role(
    user_id: uuid.UUID,
    payload: MemberRoleUpdate,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> MemberRead:
    return MemberRead.model_validate(
        ProjectService(db).change_member_role(
            project, user_id, payload.role, current_user, ctx
        )
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=MessageResponse,
    summary="Remove a member",
)
def remove_member(
    user_id: uuid.UUID,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> MessageResponse:
    ProjectService(db).remove_member(project, user_id, current_user, ctx)
    return MessageResponse(message="Member removed.")
