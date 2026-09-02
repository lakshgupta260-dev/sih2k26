"""Extraction and matching orchestration, and human review.

Owns the transaction boundary and the translation between ORM rows and the
ORM-free value objects the AI layer works with. The engine itself knows nothing
about the database; everything database-shaped happens here.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.base import parse_chainage, parse_joints
from app.ai.extraction.rules import RuleBasedExtractor
from app.ai.matching.engine import ActivityMatcher
from app.ai.providers.embeddings import get_embedding_provider
from app.ai.providers.llm import get_llm_provider
from app.ai.schemas import ActivityRef, ExtractedItem, MatchOutcome
from app.core.config import settings
from app.core.constants import AuditAction, MatchStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.document import ProgressReport
from app.models.matching import ActivityMatch, ExtractedActivity
from app.models.project import Project
from app.models.schedule import Activity, Schedule
from app.models.user import User
from app.repositories.matching import (
    ActivityMatchRepository,
    ExtractedActivityRepository,
)
from app.schemas.matching import (
    MatchReviewDecision,
    MatchRunRequest,
    MatchRunSummary,
    MatchStatsRead,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.project import ProjectService

logger = get_logger(__name__)


class MatchingService:
    """Turns stored progress reports into linked, reviewable activity events."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.extracted = ExtractedActivityRepository(db)
        self.matches = ActivityMatchRepository(db)
        self.projects = ProjectService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------- plan side
    def _activity_refs(self, schedule_id: uuid.UUID) -> list[ActivityRef]:
        """Project plan activities into ORM-free refs.

        Chainage and joint bands are parsed from the activity name with the
        same parsers used on the field side. Phase 3 does not store them as
        columns, and parsing both sides identically is what makes the location
        signal trustworthy -- a different parser on each side would silently
        disagree.
        """
        rows = (
            self.db.execute(select(Activity).where(Activity.schedule_id == schedule_id))
            .scalars()
            .all()
        )
        refs: list[ActivityRef] = []
        for row in rows:
            refs.append(
                ActivityRef(
                    id=str(row.id),
                    activity_code=row.activity_code,
                    name=row.name,
                    wbs_path=row.wbs_path or "",
                    level=row.level,
                    discipline=str(row.discipline) if row.discipline else None,
                    chainage=parse_chainage(row.name),
                    joints=parse_joints(row.name),
                )
            )
        return refs

    def _resolve_schedule(self, project: Project, schedule_id: uuid.UUID | None) -> Schedule:
        if schedule_id:
            schedule = self.db.execute(
                select(Schedule).where(
                    Schedule.id == schedule_id,
                    Schedule.project_id == project.id,
                    Schedule.is_deleted.is_(False),
                )
            ).scalar_one_or_none()
            if schedule is None:
                raise NotFoundError("Schedule not found in this project.")
            return schedule

        schedule = self.db.execute(
            select(Schedule)
            .where(Schedule.project_id == project.id, Schedule.is_deleted.is_(False))
            .order_by(Schedule.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if schedule is None:
            raise ValidationError(
                "This project has no schedule to match against. Upload one first.",
                code="NO_SCHEDULE",
            )
        return schedule

    # ------------------------------------------------------------ field side
    def _reports_to_process(
        self, project: Project, request: MatchRunRequest
    ) -> Sequence[ProgressReport]:
        stmt = select(ProgressReport).where(ProgressReport.project_id == project.id)
        if request.progress_report_id:
            stmt = stmt.where(ProgressReport.id == request.progress_report_id)
        reports = self.db.execute(stmt.order_by(ProgressReport.created_at)).scalars().all()

        if request.progress_report_id and not reports:
            raise NotFoundError("Progress report not found in this project.")
        if request.reprocess:
            return reports
        # Skip reports that already produced items, so a re-run is cheap and
        # does not duplicate rows.
        return [r for r in reports if self.extracted.count_for_report(r.id) == 0]

    @staticmethod
    def _to_item_rows(
        report: ProgressReport, items: list[ExtractedItem]
    ) -> list[dict]:
        rows = []
        for item in items:
            rows.append(
                dict(
                    project_id=report.project_id,
                    progress_report_id=report.id,
                    source_ref=item.source_ref,
                    raw_text=item.raw_text[:8000],
                    event_type=item.event_type.value,
                    activity_code=item.activity_code,
                    description=(item.description or "")[:8000] or None,
                    discipline=item.discipline,
                    event_date=item.event_date or report.report_date,
                    percent_complete=item.percent_complete,
                    quantity=item.quantity,
                    uom=item.uom,
                    chainage_from_m=item.chainage.from_m if item.chainage else None,
                    chainage_to_m=item.chainage.to_m if item.chainage else None,
                    joint_from=item.joints.from_no if item.joints else None,
                    joint_to=item.joints.to_no if item.joints else None,
                    extraction_confidence=item.extraction_confidence,
                    extractor=item.extractor,
                    notes=item.notes,
                )
            )
        return rows

    @staticmethod
    def _candidate_payload(outcome: MatchOutcome) -> list[dict]:
        return [
            {
                "activity_id": c.activity.id,
                "activity_code": c.activity.activity_code,
                "activity_name": c.activity.name,
                "wbs_path": c.activity.wbs_path,
                "level": c.activity.level,
                "score": c.score,
                "method": str(c.method),
                "signals": c.signals.as_dict(),
                "explanation": c.explanation,
            }
            for c in outcome.candidates
        ]

    # ------------------------------------------------------------------- run
    def run(
        self,
        project_id: uuid.UUID,
        request: MatchRunRequest,
        actor: User,
        ctx: RequestContext,
    ) -> MatchRunSummary:
        """Extract from reports and link the results to plan activities."""
        project = self.projects.get_for_user(project_id, actor)
        schedule = self._resolve_schedule(project, request.schedule_id)
        refs = self._activity_refs(schedule.id)
        if not refs:
            raise ValidationError(
                "The selected schedule has no activities to match against.",
                code="EMPTY_SCHEDULE",
            )

        reports = self._reports_to_process(project, request)
        embeddings = get_embedding_provider()
        llm = get_llm_provider()
        matcher = ActivityMatcher(
            refs,
            embedding_provider=embeddings,
            auto_threshold=request.auto_threshold,
            review_threshold=request.review_threshold,
        )
        extractor = RuleBasedExtractor()

        totals = {
            MatchStatus.AUTO_MATCHED: 0,
            MatchStatus.NEEDS_REVIEW: 0,
            MatchStatus.UNMATCHED: 0,
        }
        items_extracted = 0
        matches_created = 0
        extractors_used: set[str] = set()

        for report in reports:
            if request.reprocess:
                existing = self.extracted.list_for_report(report.id)
                self.matches.delete_for_extracted([e.id for e in existing])
                self.extracted.delete_for_report(report.id)

            items = extractor.extract(report.raw_text or "", source=f"report:{report.id}")
            if not items:
                continue
            extractors_used.add(extractor.name)

            rows = self._to_item_rows(report, items)
            orm_items = [ExtractedActivity(**row) for row in rows]
            self.db.add_all(orm_items)
            self.db.flush()
            items_extracted += len(orm_items)

            outcomes = matcher.match_all(items)
            for orm_item, outcome in zip(orm_items, outcomes):
                best = outcome.best
                status = outcome.status
                self.db.add(
                    ActivityMatch(
                        project_id=project.id,
                        extracted_activity_id=orm_item.id,
                        activity_id=(
                            uuid.UUID(best.activity.id)
                            if best and status != MatchStatus.UNMATCHED
                            else None
                        ),
                        status=status,
                        auto_status=status,
                        method=str(best.method) if best else "HYBRID",
                        score=best.score if best else 0.0,
                        reason=outcome.reason,
                        signals=best.signals.as_dict() if best else {},
                        candidates=self._candidate_payload(outcome),
                        embedding_provider=getattr(embeddings, "name", None),
                    )
                )
                matches_created += 1
                totals[status] = totals.get(status, 0) + 1

        self.audit.record(
            action="MATCH_RUN",
            entity_type="project",
            entity_id=project.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={
                "schedule_id": str(schedule.id),
                "reports_processed": len(reports),
                "items_extracted": items_extracted,
                "matches_created": matches_created,
                "auto_matched": totals[MatchStatus.AUTO_MATCHED],
                "needs_review": totals[MatchStatus.NEEDS_REVIEW],
                "unmatched": totals[MatchStatus.UNMATCHED],
                "extractors": sorted(extractors_used),
                "embedding_provider": getattr(embeddings, "name", "?"),
                "llm_available": llm.is_available(),
            },
        )
        self.db.commit()

        return MatchRunSummary(
            reports_processed=len(reports),
            items_extracted=items_extracted,
            matches_created=matches_created,
            auto_matched=totals[MatchStatus.AUTO_MATCHED],
            needs_review=totals[MatchStatus.NEEDS_REVIEW],
            unmatched=totals[MatchStatus.UNMATCHED],
            schedule_id=schedule.id,
            extractors_used=sorted(extractors_used),
            embedding_provider=getattr(embeddings, "name", "?"),
            llm_available=llm.is_available(),
            auto_threshold=(
                request.auto_threshold
                if request.auto_threshold is not None
                else settings.MATCH_AUTO_THRESHOLD
            ),
            review_threshold=(
                request.review_threshold
                if request.review_threshold is not None
                else settings.MATCH_REVIEW_THRESHOLD
            ),
        )

    # ---------------------------------------------------------------- review
    def get_match(self, project_id: uuid.UUID, match_id: uuid.UUID, actor: User) -> ActivityMatch:
        self.projects.get_for_user(project_id, actor)
        match = self.matches.get_with_extracted(match_id)
        if match is None or match.project_id != project_id:
            raise NotFoundError("Match not found.")
        return match

    def review(
        self,
        project_id: uuid.UUID,
        match_id: uuid.UUID,
        decision: MatchReviewDecision,
        actor: User,
        ctx: RequestContext,
    ) -> ActivityMatch:
        """Record a human verdict, preserving the machine's original one."""
        # Reviewing changes what the schedule believes, so it needs the same
        # authority as editing the project.
        self.projects.require_project_admin(project_id, actor)
        match = self.matches.get_with_extracted(match_id)
        if match is None or match.project_id != project_id:
            raise NotFoundError("Match not found.")

        previous_status = match.status
        previous_activity = match.activity_id

        if decision.decision == "confirm":
            if match.activity_id is None:
                raise ValidationError(
                    "This match has no proposed activity to confirm. Reassign it instead.",
                    code="NOTHING_TO_CONFIRM",
                )
            match.status = MatchStatus.MANUALLY_CONFIRMED
        elif decision.decision == "reject":
            match.status = MatchStatus.MANUALLY_REJECTED
            match.activity_id = None
        else:  # reassign
            target = self.db.get(Activity, decision.activity_id)
            if target is None:
                raise NotFoundError("Target activity not found.")
            schedule = self.db.get(Schedule, target.schedule_id)
            # Without this check a reviewer could point a line at an activity
            # in someone else's project.
            if schedule is None or schedule.project_id != project_id:
                raise ValidationError(
                    "The target activity belongs to a different project.",
                    code="CROSS_PROJECT_ACTIVITY",
                )
            match.activity_id = target.id
            match.status = MatchStatus.MANUALLY_CONFIRMED

        match.reviewed_by_id = actor.id
        match.reviewed_at = datetime.now(UTC)
        match.review_note = decision.note
        self.db.add(match)

        self.audit.record(
            action=(
                AuditAction.MATCH_CONFIRM
                if match.status == MatchStatus.MANUALLY_CONFIRMED
                else AuditAction.MATCH_REJECT
            ),
            entity_type="activity_match",
            entity_id=match.id,
            actor_user_id=actor.id,
            project_id=project_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={
                "decision": decision.decision,
                "from_status": str(previous_status),
                "to_status": str(match.status),
                "from_activity_id": str(previous_activity) if previous_activity else None,
                "to_activity_id": str(match.activity_id) if match.activity_id else None,
                "machine_status": str(match.auto_status),
                "machine_score": match.score,
                "note": decision.note,
            },
        )
        self.db.commit()
        self.db.refresh(match)
        return match

    def history(
        self, project_id: uuid.UUID, match_id: uuid.UUID, actor: User
    ) -> list[dict]:
        """Every recorded decision on one match, oldest first."""
        self.projects.get_for_user(project_id, actor)
        from app.models.audit import AuditLog

        rows = (
            self.db.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "activity_match",
                    AuditLog.entity_id == str(match_id),
                )
                .order_by(AuditLog.created_at)
            )
            .scalars()
            .all()
        )
        return [
            {
                "action": row.action,
                "actor_user_id": row.actor_user_id,
                "created_at": row.created_at,
                "details": row.details,
            }
            for row in rows
        ]

    def stats(self, project_id: uuid.UUID, actor: User) -> MatchStatsRead:
        self.projects.get_for_user(project_id, actor)
        counts = self.matches.status_counts(project_id)
        upheld, reviewed = self.matches.auto_review_agreement(project_id)
        return MatchStatsRead(
            total=sum(counts.values()),
            auto_matched=counts.get(MatchStatus.AUTO_MATCHED, 0),
            needs_review=counts.get(MatchStatus.NEEDS_REVIEW, 0),
            unmatched=counts.get(MatchStatus.UNMATCHED, 0),
            manually_confirmed=counts.get(MatchStatus.MANUALLY_CONFIRMED, 0),
            manually_rejected=counts.get(MatchStatus.MANUALLY_REJECTED, 0),
            auto_precision=(upheld / reviewed) if reviewed else None,
            reviewed_count=reviewed,
        )
