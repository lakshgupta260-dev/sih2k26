"""Activities API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.schedule import ActivityRead, ActivityWithDependencies, ActivityTreeNode
from app.services.schedule import ScheduleService

router = APIRouter(prefix="/schedules/{schedule_id}/activities", tags=["activities"])


@router.get(
    "",
    response_model=Page[ActivityRead],
    summary="List schedule activities",
)
def list_activities(
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination
) -> Page[ActivityRead]:
    service = ScheduleService(db)
    activities, total = service.list_activities(schedule_id, current_user, skip=page.skip, limit=page.limit)
    items = [ActivityRead.model_validate(a) for a in activities]
    return Page[ActivityRead](
        items=items, total=total, skip=page.skip, limit=page.limit
    )


@router.get(
    "/tree",
    response_model=list[ActivityTreeNode],
    summary="Get activities as a hierarchical tree",
)
def get_activities_tree(
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser
) -> list[ActivityTreeNode]:
    service = ScheduleService(db)
    activities, _ = service.list_activities(schedule_id, current_user, skip=0, limit=10000)
    
    # Build tree.
    # ActivityTreeNode inherits from_attributes=True, so model_validate()
    # already populates `children` from the ORM relationship. The explicit
    # linking below would then append each child a second time, so the
    # relationship-loaded list is discarded first and the tree is built from
    # parent_id alone -- one source of truth.
    nodes = {}
    for activity in activities:
        node = ActivityTreeNode.model_validate(activity)
        node.children = []
        nodes[activity.id] = node
    roots = []
    
    for a in activities:
        node = nodes[a.id]
        if a.parent_id and a.parent_id in nodes:
            nodes[a.parent_id].children.append(node)
        else:
            roots.append(node)
            
    return roots


@router.get(
    "/{activity_id}",
    response_model=ActivityWithDependencies,
    summary="Get activity details including dependencies",
)
def get_activity(
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser
) -> ActivityWithDependencies:
    service = ScheduleService(db)
    activity = service.get_activity_for_user(activity_id, current_user)
    return ActivityWithDependencies.model_validate(activity)
