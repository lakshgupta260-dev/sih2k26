"""Recording actual progress and deriving planned-vs-actual analytics.

Two rules shape this module.

**Every read and write is scoped by the project the caller reached it
through.** The routers hand in a :class:`Project` already resolved by the
``AccessibleProject`` / ``ManagedProject`` guards; this service then proves the
schedule belongs to that project and the activity belongs to that schedule
before touching anything. A stale or guessed id therefore produces a 404
rather than another project's data.

**Nothing here invents a number.** Where the plan has no dates, the planned
curve is not drawn; where no one has reported yet, the actual curve stops
rather than being extrapolated flat. An analytics endpoint that fabricates a
plausible shape is worse than one that returns nothing, because the fabrication
is indistinguishable from a measurement.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.schemas import EventType
from app.core.constants import ActivityStatus, AuditAction, MatchStatus
from app.core.exceptions import NotFoundError
from app.models.matching import ActivityMatch, ExtractedActivity
from app.models.progress import ActualProgress
from app.models.project import Project
from app.models.schedule import Activity, Schedule
from app.models.user import User
from app.schemas.analytics import AnalyticsSummary, SCurvePoint
from app.schemas.progress import (
    ActivityProgressRollup,
    ActualProgressCreate,
    MatchApplicationSummary,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext

# Sampling interval for the S-curve. Weekly matches how DPRs arrive on a
# pipeline job; finer buckets add noise, coarser ones hide slippage.
_SAMPLE_DAYS = 7
# A schedule deeper than this is a data error, not a real WBS. The bound also
# makes the traversal safe against a parent_id cycle.
_MAX_DEPTH = 64


class ProgressService:
    """Progress writes and the analytics derived from them."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # scoping helpers
    # ------------------------------------------------------------------

    def _schedule_in_project(self, project: Project, schedule_id: uuid.UUID) -> Schedule:
        """Load a schedule that genuinely belongs to *project*, else 404.

        Checking the parent link rather than just the id is what stops a
        caller from reading another project's schedule by pairing its id with
        a project they do have access to.
        """
        schedule = self.db.execute(
            select(Schedule).where(
                Schedule.id == schedule_id,
                Schedule.project_id == project.id,
                Schedule.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if schedule is None:
            raise NotFoundError("Schedule not found.", details={"schedule_id": str(schedule_id)})
        return schedule

    def _activity_in_schedule(self, schedule: Schedule, activity_id: uuid.UUID) -> Activity:
        activity = self.db.execute(
            select(Activity).where(
                Activity.id == activity_id,
                Activity.schedule_id == schedule.id,
            )
        ).scalar_one_or_none()
        if activity is None:
            raise NotFoundError("Activity not found.", details={"activity_id": str(activity_id)})
        return activity

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def record_progress(
        self,
        project: Project,
        schedule_id: uuid.UUID,
        activity_id: uuid.UUID,
        payload: ActualProgressCreate,
        actor: User,
        ctx: RequestContext,
    ) -> ActualProgress:
        """Upsert the progress record for one activity on one reporting date.

        One row per activity per date is deliberate: a DPR that restates a
        figure corrects the day's record instead of appending a second,
        contradictory one. The previous value is kept in the audit entry, so
        the correction is still traceable.
        """
        schedule = self._schedule_in_project(project, schedule_id)
        activity = self._activity_in_schedule(schedule, activity_id)

        existing = self.db.execute(
            select(ActualProgress).where(
                ActualProgress.activity_id == activity.id,
                ActualProgress.reporting_date == payload.reporting_date,
            )
        ).scalar_one_or_none()

        if existing is not None:
            previous = {
                "actual_quantity": existing.actual_quantity,
                "percent_complete": existing.percent_complete,
                "status": str(existing.status),
                "actual_start": existing.actual_start.isoformat() if existing.actual_start else None,
                "actual_finish": existing.actual_finish.isoformat() if existing.actual_finish else None,
            }
            existing.actual_quantity = payload.actual_quantity
            existing.percent_complete = payload.percent_complete
            existing.actual_start = payload.actual_start
            existing.actual_finish = payload.actual_finish
            existing.status = payload.status
            existing.notes = payload.notes
            if payload.source_report_id is not None:
                existing.source_report_id = payload.source_report_id
            existing.reported_by_id = actor.id
            progress = existing
            action = AuditAction.UPDATE
        else:
            previous = None
            progress = ActualProgress(
                activity_id=activity.id,
                reporting_date=payload.reporting_date,
                actual_quantity=payload.actual_quantity,
                percent_complete=payload.percent_complete,
                actual_start=payload.actual_start,
                actual_finish=payload.actual_finish,
                status=payload.status,
                notes=payload.notes,
                source_report_id=payload.source_report_id,
                reported_by_id=actor.id,
            )
            self.db.add(progress)
            action = AuditAction.CREATE

        self.db.flush()

        # Recorded in the caller's transaction, so a failed write leaves no
        # audit entry claiming it succeeded.
        self.audit.record(
            action=action,
            entity_type="actual_progress",
            entity_id=progress.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details={
                "activity_id": str(activity.id),
                "activity_code": activity.activity_code,
                "schedule_id": str(schedule.id),
                "reporting_date": payload.reporting_date.isoformat(),
                "percent_complete": payload.percent_complete,
                "actual_quantity": payload.actual_quantity,
                "status": str(payload.status),
                "previous": previous,
            },
        )
        self.db.commit()
        self.db.refresh(progress)
        return progress

    def apply_confirmed_matches(
        self,
        project: Project,
        schedule_id: uuid.UUID,
        actor: User,
        ctx: RequestContext,
    ) -> MatchApplicationSummary:
        """Turn confirmed Phase 5 matches into progress records.

        This is the last link in the document -> extract -> match -> progress
        chain, and it is deliberately conservative:

        * only ``AUTO_MATCHED`` and ``MANUALLY_CONFIRMED`` matches are applied
          -- anything still in review, rejected or unmatched is left alone;
        * ``PLANNED_NOT_ACTUAL`` and ``NONE`` events are never applied, no
          matter how confidently they were linked, because booking a stated
          intention as an actual is the single most common way a schedule gets
          quietly corrupted;
        * an event with no date is skipped rather than dated to today, since
          guessing the reporting date silently misplaces work in time.

        Each skip is counted and named in the summary, so "why didn't my
        report show up" has an answer.
        """
        schedule = self._schedule_in_project(project, schedule_id)

        activity_ids = set(
            self.db.execute(
                select(Activity.id).where(Activity.schedule_id == schedule.id)
            ).scalars()
        )

        matches = list(
            self.db.execute(
                select(ActivityMatch)
                .options(selectinload(ActivityMatch.extracted_activity))
                .where(
                    ActivityMatch.project_id == project.id,
                    ActivityMatch.status.in_(
                        (MatchStatus.AUTO_MATCHED, MatchStatus.MANUALLY_CONFIRMED)
                    ),
                    ActivityMatch.activity_id.is_not(None),
                )
                .order_by(ActivityMatch.created_at)
            ).scalars()
        )

        applied = 0
        updated = 0
        skipped_not_actual = 0
        skipped_no_date = 0
        skipped_other_schedule = 0

        for match in matches:
            if match.activity_id not in activity_ids:
                # Confirmed against an activity in a different schedule of the
                # same project; not this schedule's business.
                skipped_other_schedule += 1
                continue

            item = match.extracted_activity
            event = item.event_type
            if event not in (
                EventType.ACTUAL_START,
                EventType.ACTUAL_FINISH,
                EventType.PROGRESS_UPDATE,
            ):
                skipped_not_actual += 1
                continue
            if item.event_date is None:
                skipped_no_date += 1
                continue

            existing = self.db.execute(
                select(ActualProgress).where(
                    ActualProgress.activity_id == match.activity_id,
                    ActualProgress.reporting_date == item.event_date,
                )
            ).scalar_one_or_none()

            row = existing or ActualProgress(
                activity_id=match.activity_id,
                reporting_date=item.event_date,
            )

            if event == EventType.ACTUAL_START:
                row.actual_start = item.event_date
                if row.status != ActivityStatus.COMPLETED:
                    row.status = ActivityStatus.IN_PROGRESS
            elif event == EventType.ACTUAL_FINISH:
                row.actual_finish = item.event_date
                row.status = ActivityStatus.COMPLETED
                # A finish event asserts completion; the plan quantity is the
                # authority on how much that is, not the report's phrasing.
                row.percent_complete = 100.0
            else:
                if item.percent_complete is not None:
                    row.percent_complete = item.percent_complete
                if item.quantity is not None:
                    row.actual_quantity = item.quantity
                if row.status == ActivityStatus.NOT_STARTED:
                    row.status = ActivityStatus.IN_PROGRESS

            row.source_report_id = item.progress_report_id
            row.reported_by_id = actor.id

            if existing is None:
                self.db.add(row)
                applied += 1
            else:
                updated += 1

        self.db.flush()

        summary = MatchApplicationSummary(
            schedule_id=schedule.id,
            matches_considered=len(matches),
            records_created=applied,
            records_updated=updated,
            skipped_not_an_actual_event=skipped_not_actual,
            skipped_missing_event_date=skipped_no_date,
            skipped_other_schedule=skipped_other_schedule,
        )

        self.audit.record(
            action="PROGRESS_APPLY_MATCHES",
            entity_type="schedule",
            entity_id=schedule.id,
            actor_user_id=actor.id,
            project_id=project.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            details=summary.model_dump(mode="json"),
        )
        self.db.commit()
        return summary

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def get_progress_history(
        self, project: Project, schedule_id: uuid.UUID, activity_id: uuid.UUID
    ) -> list[ActualProgress]:
        schedule = self._schedule_in_project(project, schedule_id)
        activity = self._activity_in_schedule(schedule, activity_id)
        return list(
            self.db.execute(
                select(ActualProgress)
                .where(ActualProgress.activity_id == activity.id)
                .order_by(ActualProgress.reporting_date.desc())
            ).scalars()
        )

    # ------------------------------------------------------------------
    # rollup
    # ------------------------------------------------------------------

    def _load_tree(self, schedule: Schedule) -> tuple[
        dict[uuid.UUID, Activity],
        dict[uuid.UUID, list[uuid.UUID]],
        list[uuid.UUID],
    ]:
        activities = list(
            self.db.execute(
                select(Activity).where(Activity.schedule_id == schedule.id)
            ).scalars()
        )
        by_id = {a.id: a for a in activities}
        children: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        roots: list[uuid.UUID] = []
        for a in activities:
            if a.parent_id is not None and a.parent_id in by_id:
                children[a.parent_id].append(a.id)
            else:
                roots.append(a.id)
        return by_id, children, roots

    def _latest_progress(self, schedule: Schedule, as_of: date | None = None
                         ) -> dict[uuid.UUID, ActualProgress]:
        """Most recent progress row per activity, optionally as at a date.

        Uses ``DISTINCT ON`` so the database returns one row per activity
        rather than the schedule's entire reporting history.

        The previous implementation selected every progress row ascending and
        let later rows overwrite earlier ones in a dict. That is correct, and
        it measured 2,391 ms on a 5,000-activity schedule with 91,470 progress
        rows -- roughly 94% of the total cost of the progress rollup -- because
        it built 91,470 ORM instances to arrive at 3,049 values. The work grew
        with reporting *history*, which is the worst shape for this query: fast
        in a demo, slower every day a real project runs.

        ``DISTINCT ON`` is PostgreSQL-specific. That is acceptable here: the
        project targets PostgreSQL and already relies on JSONB throughout.
        There is no tie to break, because ``uq_progress_activity_date`` makes
        (activity_id, reporting_date) unique, and that same index serves the
        ordering -- so this needs no new index.
        """
        stmt = (
            select(ActualProgress)
            .join(Activity, Activity.id == ActualProgress.activity_id)
            .where(Activity.schedule_id == schedule.id)
        )
        if as_of is not None:
            stmt = stmt.where(ActualProgress.reporting_date <= as_of)

        # DISTINCT ON requires its expression to lead the ORDER BY.
        stmt = stmt.order_by(
            ActualProgress.activity_id, ActualProgress.reporting_date.desc()
        ).distinct(ActualProgress.activity_id)

        return {row.activity_id: row for row in self.db.execute(stmt).scalars()}

    @staticmethod
    def _weight(activity: Activity) -> float:
        """How much a leaf counts toward its parent.

        Budgeted quantity when the plan gives one, so 40 km of trenching does
        not weigh the same as a single survey task. Falling back to 1.0 makes
        an unquantified schedule degrade to a plain activity count rather than
        vanishing from the rollup.
        """
        qty = activity.budgeted_quantity
        if qty is not None and qty > 0:
            return float(qty)
        return 1.0

    @staticmethod
    def _completion(activity: Activity, progress: ActualProgress | None) -> float:
        """Fraction 0..1 complete for a leaf activity.

        Quantity is preferred over percentage because it is measured rather
        than estimated, but only when the plan states a budget to measure it
        against. Note the ``is not None`` tests: a genuine reported quantity of
        zero means "nothing done yet", not "nothing reported".
        """
        if progress is None:
            return 0.0
        budget = activity.budgeted_quantity
        if budget is not None and budget > 0 and progress.actual_quantity is not None:
            return max(0.0, min(1.0, progress.actual_quantity / budget))
        if progress.percent_complete is not None:
            return max(0.0, min(1.0, progress.percent_complete / 100.0))
        if progress.status == ActivityStatus.COMPLETED:
            return 1.0
        return 0.0

    def _rollup_weights(
        self,
        by_id: dict[uuid.UUID, Activity],
        children: dict[uuid.UUID, list[uuid.UUID]],
        roots: list[uuid.UUID],
        latest: dict[uuid.UUID, ActualProgress],
        today: date,
    ) -> tuple[dict[uuid.UUID, tuple[float, float]], dict[uuid.UUID, bool]]:
        """One post-order pass computing (earned, weight) and delay per node.

        Iterative rather than recursive, and each node is visited once, so a
        deep 5,000-activity WBS costs a single traversal instead of one
        subtree walk per activity.
        """
        totals: dict[uuid.UUID, tuple[float, float]] = {}
        delayed: dict[uuid.UUID, bool] = {}

        # Explicit stack: (node, depth, children_expanded)
        for root in roots:
            stack: list[tuple[uuid.UUID, int, bool]] = [(root, 0, False)]
            while stack:
                node_id, depth, expanded = stack.pop()
                if node_id in totals:
                    continue
                kids = children.get(node_id, ())
                if kids and not expanded and depth < _MAX_DEPTH:
                    stack.append((node_id, depth, True))
                    for kid in kids:
                        if kid not in totals:
                            stack.append((kid, depth + 1, False))
                    continue

                activity = by_id[node_id]
                # Treat a node whose children were not expanded (depth bound
                # hit) as a leaf rather than reporting nothing for it.
                resolved = [k for k in kids if k in totals]
                if resolved:
                    earned = sum(totals[k][0] for k in resolved)
                    weight = sum(totals[k][1] for k in resolved)
                    is_delayed = any(delayed[k] for k in resolved)
                else:
                    progress = latest.get(node_id)
                    weight = self._weight(activity)
                    earned = self._completion(activity, progress) * weight
                    is_delayed = self._leaf_delayed(activity, progress, today)

                totals[node_id] = (earned, weight)
                delayed[node_id] = is_delayed

        # Orphans left by a parent_id cycle still deserve a row.
        for node_id, activity in by_id.items():
            if node_id not in totals:
                progress = latest.get(node_id)
                weight = self._weight(activity)
                totals[node_id] = (self._completion(activity, progress) * weight, weight)
                delayed[node_id] = self._leaf_delayed(activity, progress, today)

        return totals, delayed

    @staticmethod
    def _leaf_delayed(activity: Activity, progress: ActualProgress | None, today: date) -> bool:
        if activity.planned_finish is None:
            return False
        if progress is not None:
            if progress.actual_finish is not None:
                return progress.actual_finish > activity.planned_finish
            if progress.status == ActivityStatus.COMPLETED:
                return False
        return today > activity.planned_finish

    def get_project_rollup(
        self, project: Project, schedule_id: uuid.UUID, as_of: date | None = None
    ) -> list[ActivityProgressRollup]:
        schedule = self._schedule_in_project(project, schedule_id)
        by_id, children, roots = self._load_tree(schedule)
        if not by_id:
            return []

        today = as_of or date.today()
        latest = self._latest_progress(schedule, as_of=as_of)
        totals, delayed = self._rollup_weights(by_id, children, roots, latest, today)

        rollups = []
        for node_id, activity in by_id.items():
            earned, weight = totals[node_id]
            progress = latest.get(node_id)
            rollups.append(
                ActivityProgressRollup(
                    activity_id=node_id,
                    activity_code=activity.activity_code,
                    name=activity.name,
                    wbs_path=activity.wbs_path,
                    level=activity.level,
                    completion_percentage=(earned / weight * 100.0) if weight > 0 else 0.0,
                    status=progress.status if progress else ActivityStatus.NOT_STARTED,
                    is_delayed=delayed[node_id],
                    is_leaf=not children.get(node_id),
                    weight=weight,
                )
            )
        return sorted(rollups, key=lambda r: _wbs_sort_key(r.wbs_path))

    # ------------------------------------------------------------------
    # analytics
    # ------------------------------------------------------------------

    def _planned_fraction(self, activity: Activity, at: date) -> float:
        """Share of a leaf's work the plan expects done by *at*.

        Linear within the planned window. A real plan may front- or back-load
        effort, but the schedule as ingested carries only start and finish, so
        linear is the only distribution the data actually supports -- assuming
        an S-shape here would be inventing a curve the plan never stated.
        """
        start, finish = activity.planned_start, activity.planned_finish
        if start is None or finish is None:
            return 0.0
        if at < start:
            return 0.0
        if at >= finish:
            return 1.0
        span = (finish - start).days
        if span <= 0:
            return 1.0
        return (at - start).days / span

    def generate_s_curve(
        self, project: Project, schedule_id: uuid.UUID
    ) -> list[SCurvePoint]:
        """Cumulative planned vs actual completion, sampled weekly.

        Planned comes from the leaf activities' planned windows weighted by
        budgeted quantity. Actual comes from the reported rows, carried forward
        between reports the way a cumulative figure behaves.

        ``actual_percentage`` is ``None`` for any sample after the last
        reporting date: beyond that point nothing has been measured, and
        drawing the last known value forward would show a flat actual line
        that looks like a stall we observed rather than an absence of data.
        Returns an empty list when the plan carries no dates at all.
        """
        schedule = self._schedule_in_project(project, schedule_id)
        by_id, children, _ = self._load_tree(schedule)
        leaves = [a for nid, a in by_id.items() if not children.get(nid)]
        if not leaves:
            return []

        dated = [a for a in leaves if a.planned_start and a.planned_finish]
        if not dated:
            # No planned window anywhere: a planned curve would be fabricated.
            return []

        total_weight = sum(self._weight(a) for a in leaves)
        if total_weight <= 0:
            return []

        # All progress rows for the schedule in date order. Unlike the rollup,
        # the curve genuinely needs the whole history: every sample point asks
        # what was true on a different past date.
        #
        # Selected as columns rather than as ORM entities, which profiling
        # showed to be the dominant cost: hydrating 91,470 ActualProgress
        # instances spent 3.34s of a 5.24s call inside the ORM loader, 1.37s of
        # it parsing 289,362 UUIDs -- three per row, when the curve reads only
        # one. These five columns are exactly what the loop below and
        # ``_completion`` touch, and a SQLAlchemy ``Row`` exposes them by the
        # same attribute names, so ``_completion`` needs no adapter and keeps
        # working unchanged with real ORM instances elsewhere.
        rows = list(
            self.db.execute(
                select(
                    ActualProgress.activity_id,
                    ActualProgress.reporting_date,
                    ActualProgress.actual_quantity,
                    ActualProgress.percent_complete,
                    ActualProgress.status,
                )
                .join(Activity, Activity.id == ActualProgress.activity_id)
                .where(Activity.schedule_id == schedule.id)
                .order_by(ActualProgress.reporting_date.asc())
            )
        )

        # Hoisted out of the sample loop below. Recomputing these per sample
        # meant a full pass over every progress row for each of ~150 samples --
        # 13.7M redundant comparisons on the benchmark schedule, for two values
        # that cannot change.
        last_report = max((r.reporting_date for r in rows), default=None)
        first_report = min((r.reporting_date for r in rows), default=None)

        leaf_by_id = {a.id: a for a in leaves}

        start = min(a.planned_start for a in dated)
        end = max(a.planned_finish for a in dated)
        if last_report and last_report > end:
            end = last_report

        samples: list[date] = []
        cursor = start
        while cursor < end:
            samples.append(cursor)
            cursor = date.fromordinal(cursor.toordinal() + _SAMPLE_DAYS)
        samples.append(end)

        # Samples ascend and ``rows`` is already date-ascending, so the earned
        # total is maintained with one forward pass over the history shared
        # across every sample: each row is visited exactly once overall.
        #
        # The previous shape re-scanned every leaf's history for every sample
        # -- O(samples x leaves x history), up to 13.7M inner iterations on the
        # benchmark schedule. This is O(history + samples).
        #
        # Correctness rests on date ordering: a later row for the same activity
        # is processed after an earlier one, so replacing that activity's
        # contribution leaves the latest report at or before the sample date,
        # which is what the earlier nested scan selected.
        row_pointer = 0
        contribution: dict[uuid.UUID, float] = {}
        earned = 0.0

        points: list[SCurvePoint] = []
        for at in samples:
            planned = sum(
                self._planned_fraction(a, at) * self._weight(a) for a in leaves
            )

            while row_pointer < len(rows) and rows[row_pointer].reporting_date <= at:
                row = rows[row_pointer]
                row_pointer += 1
                leaf = leaf_by_id.get(row.activity_id)
                if leaf is None:
                    # Progress against a parent node does not belong in a
                    # leaf-weighted curve; the rollup handles those.
                    continue
                updated = self._completion(leaf, row) * self._weight(leaf)
                earned += updated - contribution.get(row.activity_id, 0.0)
                contribution[row.activity_id] = updated

            actual: float | None = None
            if (
                last_report is not None
                and first_report is not None
                and first_report <= at <= last_report
            ):
                actual = earned / total_weight * 100.0
            points.append(
                SCurvePoint(
                    reporting_date=at,
                    planned_percentage=planned / total_weight * 100.0,
                    actual_percentage=actual,
                )
            )
        return points

    def get_summary(
        self, project: Project, schedule_id: uuid.UUID, as_of: date | None = None
    ) -> AnalyticsSummary:
        """Headline figures, all weighted consistently with the rollup."""
        schedule = self._schedule_in_project(project, schedule_id)
        by_id, children, roots = self._load_tree(schedule)
        today = as_of or date.today()

        if not by_id:
            return AnalyticsSummary(
                as_of=today,
                total_activities=0,
                leaf_activities=0,
                completed_activities=0,
                delayed_activities=0,
                overall_completion_percentage=0.0,
                planned_completion_percentage=None,
                schedule_variance=None,
                activities_with_progress=0,
                last_reported_on=None,
            )

        latest = self._latest_progress(schedule, as_of=as_of)
        totals, delayed = self._rollup_weights(by_id, children, roots, latest, today)

        leaf_ids = [nid for nid in by_id if not children.get(nid)]

        # Overall completion is the weighted roll-up over the roots, not an
        # unweighted mean of the top-level nodes: a 40 km spread must not count
        # the same as a one-off survey task.
        earned = sum(totals[r][0] for r in roots) if roots else 0.0
        weight = sum(totals[r][1] for r in roots) if roots else 0.0
        if not roots:
            earned = sum(totals[i][0] for i in leaf_ids)
            weight = sum(totals[i][1] for i in leaf_ids)
        overall = (earned / weight * 100.0) if weight > 0 else 0.0

        leaves = [by_id[i] for i in leaf_ids]
        dated = [a for a in leaves if a.planned_start and a.planned_finish]
        planned_pct: float | None = None
        if dated:
            leaf_weight = sum(self._weight(a) for a in leaves)
            if leaf_weight > 0:
                planned_pct = (
                    sum(self._planned_fraction(a, today) * self._weight(a) for a in leaves)
                    / leaf_weight
                    * 100.0
                )

        return AnalyticsSummary(
            as_of=today,
            total_activities=len(by_id),
            leaf_activities=len(leaf_ids),
            completed_activities=sum(
                1 for i in leaf_ids
                if (p := latest.get(i)) is not None and p.status == ActivityStatus.COMPLETED
            ),
            delayed_activities=sum(1 for i in leaf_ids if delayed[i]),
            overall_completion_percentage=overall,
            planned_completion_percentage=planned_pct,
            # Negative means behind plan. Null when the plan carries no dates,
            # because there is then nothing to be ahead or behind of.
            schedule_variance=None if planned_pct is None else overall - planned_pct,
            activities_with_progress=len([i for i in leaf_ids if i in latest]),
            last_reported_on=max((p.reporting_date for p in latest.values()), default=None),
        )


def _wbs_sort_key(path: str) -> tuple[object, ...]:
    """Order WBS paths numerically, so 1.9 precedes 1.10.

    Plain string ordering puts "1.10" before "1.9", which reads as corrupted
    data to a planner. Segments that are not numeric fall back to text.
    """
    key: list[object] = []
    for segment in path.split("."):
        if segment.isdigit():
            key.append((0, int(segment), ""))
        else:
            key.append((1, 0, segment))
    return tuple(key)
