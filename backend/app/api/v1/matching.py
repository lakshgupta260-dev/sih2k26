"""Extraction, matching and human-review endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import Ctx, CurrentUser, DbSession, ManagedProject, Pagination
from app.core.constants import MatchStatus
from app.schemas.common import Page
from app.schemas.matching import (
    ActivityMatchDetail,
    ActivityMatchRead,
    AuditEntryRead,
    ExtractedActivityRead,
    MatchReviewDecision,
    MatchRunRequest,
    MatchRunSummary,
    MatchStatsRead,
)
from app.services.matching import MatchingService

router = APIRouter(prefix="/projects/{project_id}/matching", tags=["matching"])


@router.post(
    "/run",
    response_model=MatchRunSummary,
    status_code=status.HTTP_200_OK,
    summary="Extract activity events from progress reports and link them",
    description=(
        "Runs the extractor over stored progress reports, then links each "
        "extracted event to a plan activity. Thresholds may be overridden per "
        "run. The response states which extractor and embedding provider "
        "actually ran, and whether an LLM was available, so a result is never "
        "ambiguous about how it was produced.\n\n"
        "Requires the project manager role. Runs synchronously for a single "
        "report; use the Celery task for a whole project."
    ),
)
def run_matching(
    payload: MatchRunRequest,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> MatchRunSummary:
    return MatchingService(db).run(project.id, payload, current_user, ctx)


@router.get(
    "/matches",
    response_model=Page[ActivityMatchDetail],
    summary="List matches, optionally filtered by status",
    description=(
        "Pass `status=NEEDS_REVIEW` for the review queue. Ordered by score "
        "descending, so the clearest decisions come first."
    ),
)
def list_matches(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination,
    status_filter: MatchStatus | None = Query(default=None, alias="status"),
) -> Page[ActivityMatchDetail]:
    service = MatchingService(db)
    service.projects.get_for_user(project_id, current_user)
    rows = service.matches.list_for_project(
        project_id,
        status=status_filter.value if status_filter else None,
        skip=page.skip,
        limit=page.limit,
    )
    total = service.matches.count_for_project(
        project_id, status=status_filter.value if status_filter else None
    )
    items = [
        ActivityMatchDetail(
            **ActivityMatchRead.model_validate(row).model_dump(),
            extracted=ExtractedActivityRead.model_validate(row.extracted_activity),
        )
        for row in rows
    ]
    return Page[ActivityMatchDetail](
        items=items, total=total, skip=page.skip, limit=page.limit
    )


@router.get(
    "/matches/{match_id}",
    response_model=ActivityMatchDetail,
    summary="Fetch one match with its signals, candidates and source text",
)
def get_match(
    project_id: uuid.UUID,
    match_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ActivityMatchDetail:
    match = MatchingService(db).get_match(project_id, match_id, current_user)
    return ActivityMatchDetail(
        **ActivityMatchRead.model_validate(match).model_dump(),
        extracted=ExtractedActivityRead.model_validate(match.extracted_activity),
    )


@router.post(
    "/matches/{match_id}/review",
    response_model=ActivityMatchDetail,
    summary="Confirm, reject or reassign a proposed match",
    description=(
        "The machine's original verdict is preserved in `auto_status`, so the "
        "matcher's accuracy can be measured against human decisions. Every "
        "decision is written to the audit log and readable via "
        "`/matches/{id}/history`.\n\nRequires the project manager role."
    ),
)
def review_match(
    match_id: uuid.UUID,
    payload: MatchReviewDecision,
    project: ManagedProject,
    db: DbSession,
    current_user: CurrentUser,
    ctx: Ctx,
) -> ActivityMatchDetail:
    match = MatchingService(db).review(project.id, match_id, payload, current_user, ctx)
    return ActivityMatchDetail(
        **ActivityMatchRead.model_validate(match).model_dump(),
        extracted=ExtractedActivityRead.model_validate(match.extracted_activity),
    )


@router.get(
    "/matches/{match_id}/history",
    response_model=list[AuditEntryRead],
    summary="Complete review history for one match",
)
def match_history(
    project_id: uuid.UUID,
    match_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[AuditEntryRead]:
    rows = MatchingService(db).history(project_id, match_id, current_user)
    return [AuditEntryRead(**row) for row in rows]


@router.get(
    "/stats",
    response_model=MatchStatsRead,
    summary="Queue counters and measured matcher precision",
    description=(
        "`auto_precision` is the share of automatic links a human has since "
        "upheld. It is null until reviews exist -- a measured number, never an "
        "estimate."
    ),
)
def match_stats(
    project_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> MatchStatsRead:
    return MatchingService(db).stats(project_id, current_user)


@router.get(
    "/extracted",
    response_model=Page[ExtractedActivityRead],
    summary="List extracted field items, including non-events",
    description=(
        "Non-events and future-intent lines are retained deliberately: "
        "'what did this report say and what did we do with it' is the audit "
        "question that matters."
    ),
)
def list_extracted(
    project_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    page: Pagination,
) -> Page[ExtractedActivityRead]:
    from sqlalchemy import func, select

    from app.models.matching import ExtractedActivity

    service = MatchingService(db)
    service.projects.get_for_user(project_id, current_user)
    rows = (
        db.execute(
            select(ExtractedActivity)
            .where(ExtractedActivity.project_id == project_id)
            .order_by(ExtractedActivity.created_at.desc())
            .offset(page.skip)
            .limit(page.limit)
        )
        .scalars()
        .all()
    )
    total = int(
        db.execute(
            select(func.count())
            .select_from(ExtractedActivity)
            .where(ExtractedActivity.project_id == project_id)
        ).scalar_one()
    )
    return Page[ExtractedActivityRead](
        items=[ExtractedActivityRead.model_validate(r) for r in rows],
        total=total,
        skip=page.skip,
        limit=page.limit,
    )
