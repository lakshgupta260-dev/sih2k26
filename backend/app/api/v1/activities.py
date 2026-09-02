"""Activities API router.

These routes are keyed on a schedule id rather than nested under a project.
Authorization still runs through the project the schedule belongs to -- see
:meth:`app.services.schedule.ScheduleService.get_for_user` -- so a caller with
no membership gets a 404 here exactly as they would on a project-nested route.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.schedule import (
    ActivityRead,
    ActivityTreeNode,
    ActivityWithDependencies,
)
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
    page: Pagination,
) -> Page[ActivityRead]:
    service = ScheduleService(db)
    activities, total = service.list_activities(
        schedule_id, current_user, skip=page.skip, limit=page.limit
    )
    return Page[ActivityRead](
        items=[ActivityRead.model_validate(a) for a in activities],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )


@router.get(
    "/tree",
    response_model=list[ActivityTreeNode],
    summary="Activities as a hierarchical tree",
    description=(
        "The whole schedule, nested by `parent_id`. Not paginated: a tree with "
        "an offset window in it is not a tree, and a truncated list makes "
        "every activity whose parent fell outside the window look like a "
        "top-level node."
    ),
)
def get_activities_tree(
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[ActivityTreeNode]:
    service = ScheduleService(db)
    activities = service.activity_tree(schedule_id, current_user)

    # Each node is built from the flat ActivityRead fields and given an empty
    # child list, deliberately never reading the ORM `children` relationship.
    # ActivityTreeNode inherits from_attributes=True, so validating the ORM
    # object directly would populate `children` from that relationship and the
    # linking below would append every child a second time. The relationship is
    # also raiseload'ed in the repository, so touching it is an error rather
    # than a silent lazy load per activity. The tree is built from parent_id
    # alone -- one source of truth.
    nodes: dict[uuid.UUID, ActivityTreeNode] = {}
    for activity in activities:
        flat = ActivityRead.model_validate(activity).model_dump()
        nodes[activity.id] = ActivityTreeNode(**flat, children=[])

    roots: list[ActivityTreeNode] = []
    for activity in activities:
        node = nodes[activity.id]
        parent = nodes.get(activity.parent_id) if activity.parent_id else None
        if parent is not None:
            parent.children.append(node)
        else:
            roots.append(node)
    return roots


@router.get(
    "/{activity_id}",
    response_model=ActivityWithDependencies,
    summary="Activity details including dependencies",
    description=(
        "The activity must belong to the schedule in the path; an activity id "
        "from another schedule is a 404 even when the caller can see both."
    ),
)
def get_activity(
    schedule_id: uuid.UUID,
    activity_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ActivityWithDependencies:
    service = ScheduleService(db)
    activity = service.get_activity_for_user(
        activity_id, current_user, schedule_id=schedule_id
    )
    return ActivityWithDependencies.model_validate(activity)
