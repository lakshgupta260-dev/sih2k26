"""Turning a schedule and its reported progress into model inputs.

Every feature here is computed from data the platform actually ingested: the
plan's dates, quantities, disciplines and dependency graph, plus the progress
records booked against it. Nothing is synthesised, and nothing is imputed from
a distribution -- where a value is genuinely unknown the feature says so with
an explicit ``*_known`` flag rather than a silent zero, because a zero-length
planned window and an unstated one are different facts and a tree will happily
split on the difference if you let it.

The feature set is deliberately built around **rate of progress against the
rate required**, because on execution projects that ratio is what actually
predicts a late finish. Static attributes (discipline, size, level) carry far
less signal on their own, and a model given only those learns which
disciplines were historically unlucky rather than which activities are in
trouble now.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ActivityStatus, Discipline
from app.models.progress import ActualProgress
from app.models.schedule import Activity, ActivityDependency, Schedule

# Order is part of the model contract: a fitted artefact stores this list and
# refuses to score a vector built from a different one.
FEATURE_NAMES: tuple[str, ...] = (
    "planned_duration_days",
    "planned_duration_known",
    "budgeted_quantity_log",
    "budgeted_quantity_known",
    "wbs_level",
    "predecessor_count",
    "successor_count",
    "max_predecessor_slip_days",
    "predecessor_slip_known",
    "report_count",
    "days_since_last_report",
    "reporting_gap_known",
    "elapsed_fraction",
    "percent_complete",
    "planned_percent_complete",
    "progress_deficit",
    "achieved_rate_per_day",
    "required_rate_per_day",
    "rate_ratio",
    "rate_ratio_known",
    "days_remaining",
    "is_started",
    "finish_month_sin",
    "finish_month_cos",
    "is_monsoon_finish",
    "discipline_ordinal",
)

# Plain-language labels, used in the explanation payload so a planner never
# has to read a snake_case identifier.
FEATURE_LABELS: dict[str, str] = {
    "planned_duration_days": "planned duration",
    "planned_duration_known": "plan states a duration",
    "budgeted_quantity_log": "size of the activity",
    "budgeted_quantity_known": "plan states a quantity",
    "wbs_level": "WBS level",
    "predecessor_count": "number of predecessors",
    "successor_count": "number of successors",
    "max_predecessor_slip_days": "worst predecessor slip",
    "predecessor_slip_known": "predecessor finishes are known",
    "report_count": "number of progress reports",
    "days_since_last_report": "days since last report",
    "reporting_gap_known": "activity has been reported on",
    "elapsed_fraction": "share of the planned window elapsed",
    "percent_complete": "reported completion",
    "planned_percent_complete": "completion the plan expects by now",
    "progress_deficit": "completion shortfall against plan",
    "achieved_rate_per_day": "achieved rate",
    "required_rate_per_day": "rate required to finish on time",
    "rate_ratio": "achieved rate as a share of what is required",
    "rate_ratio_known": "a rate could be measured",
    "days_remaining": "days left to the planned finish",
    "is_started": "work has started",
    "finish_month_sin": "planned finish in the year (cyclic)",
    "finish_month_cos": "planned finish in the year (cyclic)",
    "is_monsoon_finish": "planned finish falls in the monsoon",
    "discipline_ordinal": "discipline",
}

# June to September. Pipeline and civil works in India lose productivity to the
# monsoon, so a finish date inside it is a real risk factor rather than an
# arbitrary calendar feature. Encoded alongside a cyclic month so the model can
# also learn ordinary seasonality.
_MONSOON_MONTHS = frozenset({6, 7, 8, 9})

_DISCIPLINE_ORDER = tuple(Discipline)

# Where through the planned window training rows are taken. Partway, so the
# outcome is still open at the moment being learned from -- see
# :meth:`FeatureBuilder.build_training_rows` for why the end of the window is
# the wrong place despite looking like the safe one.
TRAINING_CUTOFFS: tuple[float, ...] = (0.3, 0.5, 0.7)


@dataclass(slots=True)
class ActivityFeatures:
    """One row of model input, plus the facts an explanation needs.

    The raw quantities are carried alongside the vector because the rule-based
    forecast and the explanation are both stated in real units -- days, metres,
    metres per day -- and reconstructing those from a scaled feature vector
    would be lossy.
    """

    activity_id: uuid.UUID
    activity_code: str
    name: str
    wbs_path: str
    values: dict[str, float]

    # The date these features describe. Carried on the row because the
    # rule-based forecast needs it, and for a training row it is the day
    # before the activity finished rather than today.
    as_of: date | None = None
    status: ActivityStatus = ActivityStatus.NOT_STARTED
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_finish: date | None = None
    budgeted_quantity: float | None = None
    uom: str | None = None
    completed_fraction: float = 0.0
    achieved_rate: float | None = None
    required_rate: float | None = None
    days_remaining: int | None = None
    last_report_on: date | None = None
    report_count: int = 0
    max_predecessor_slip: int | None = None
    notes: list[str] = field(default_factory=list)

    def vector(self) -> list[float]:
        """The values in :data:`FEATURE_NAMES` order."""
        return [float(self.values[name]) for name in FEATURE_NAMES]

    @property
    def finished_late(self) -> bool | None:
        """The training label, or ``None`` when this row cannot be labelled.

        Only a completed activity with both a planned and an actual finish
        carries a truth. Treating an unfinished activity as "on time" would
        teach the model that everything still running is fine.
        """
        if self.status != ActivityStatus.COMPLETED:
            return None
        if self.planned_finish is None or self.actual_finish is None:
            return None
        return self.actual_finish > self.planned_finish


class FeatureBuilder:
    """Builds feature rows for a schedule as at a given date.

    ``as_of`` is explicit and load-bearing. Training rows must be built as at
    the date each activity finished, not today, or the model sees the outcome
    in its own inputs -- an activity that finished six months late has a huge
    progress deficit *because* it was late, and a model trained on today's
    snapshot would learn to read the answer off the question.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ load

    def _load(self, schedule: Schedule) -> tuple[
        list[Activity],
        dict[uuid.UUID, list[uuid.UUID]],
        dict[uuid.UUID, list[uuid.UUID]],
        dict[uuid.UUID, list[ActualProgress]],
    ]:
        activities = list(
            self.db.execute(
                select(Activity).where(Activity.schedule_id == schedule.id)
            ).scalars()
        )
        preds: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        succs: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for dep in self.db.execute(
            select(ActivityDependency).where(
                ActivityDependency.schedule_id == schedule.id
            )
        ).scalars():
            preds[dep.successor_id].append(dep.predecessor_id)
            succs[dep.predecessor_id].append(dep.successor_id)

        history: dict[uuid.UUID, list[ActualProgress]] = defaultdict(list)
        for row in self.db.execute(
            select(ActualProgress)
            .join(Activity, Activity.id == ActualProgress.activity_id)
            .where(Activity.schedule_id == schedule.id)
            .order_by(ActualProgress.reporting_date.asc())
        ).scalars():
            history[row.activity_id].append(row)
        return activities, preds, succs, history

    # -------------------------------------------------------------- building

    def build_for_schedule(
        self, schedule: Schedule, as_of: date | None = None
    ) -> list[ActivityFeatures]:
        """Feature rows for every leaf activity, as at *as_of*.

        Only leaves are included. Work is booked against leaves; a parent's
        "progress" is an aggregate, so predicting one would be predicting a
        summary of other predictions.
        """
        activities, preds, succs, history = self._load(schedule)
        if not activities:
            return []

        today = as_of or date.today()
        has_children = {a.parent_id for a in activities if a.parent_id is not None}
        by_id = {a.id: a for a in activities}

        # An activity's finish, for predecessor-slip purposes.
        finish_by_id: dict[uuid.UUID, date] = {}
        for activity in activities:
            rows = [r for r in history.get(activity.id, ()) if r.reporting_date <= today]
            finish = next(
                (r.actual_finish for r in reversed(rows) if r.actual_finish), None
            )
            if finish is not None:
                finish_by_id[activity.id] = finish

        rows_out: list[ActivityFeatures] = []
        for activity in activities:
            if activity.id in has_children:
                continue
            rows_out.append(
                self._build_one(
                    activity, today, preds, succs, history, finish_by_id, by_id
                )
            )
        return rows_out

    def build_training_rows(
        self, schedule: Schedule, cutoffs: tuple[float, ...] = TRAINING_CUTOFFS
    ) -> list[ActivityFeatures]:
        """Labelled rows, each taken at a genuine forecasting moment.

        Getting this cutoff right is the whole game, and the obvious choice is
        wrong. Building the row *just before the activity finished* looks like a
        careful leakage guard -- it is what an earlier version of this module
        did -- but it is not one. An activity that finishes late is, the day
        before it finishes, already past its planned finish with work
        outstanding. The label is then trivially readable off the features, both
        the rule-based arithmetic and any fitted model score near-perfectly, and
        neither has predicted anything.

        So rows are taken partway through the planned window instead -- at
        :data:`TRAINING_CUTOFFS` of the way through, by default 30/50/70% --
        which is when a planner actually wants an answer and when the outcome is
        genuinely still open. Several cutoffs per activity both multiply thin
        history and match the spread of elapsed fractions the model will meet
        at serving time, where an activity can be scored at any point in its
        window.

        Rows from one activity are correlated, so they carry that activity's id
        and the trainer folds on it -- see :func:`app.ml.model.train`. Splitting
        two cutoffs of the same activity across folds would leak between them.
        """
        activities, preds, succs, history = self._load(schedule)
        if not activities:
            return []

        has_children = {a.parent_id for a in activities if a.parent_id is not None}
        by_id = {a.id: a for a in activities}

        rows_out: list[ActivityFeatures] = []
        for activity in activities:
            if activity.id in has_children:
                continue
            rows = list(history.get(activity.id, ()))
            actual_finish = next(
                (r.actual_finish for r in reversed(rows) if r.actual_finish), None
            )
            if actual_finish is None:
                continue
            start, finish = activity.planned_start, activity.planned_finish
            if start is None or finish is None:
                continue
            duration = (finish - start).days
            if duration <= 0:
                continue

            for fraction in cutoffs:
                cutoff = date.fromordinal(start.toordinal() + int(duration * fraction))
                # A cutoff at or after the real finish would see the outcome.
                if cutoff >= actual_finish:
                    continue
                if cutoff <= start:
                    continue

                finish_by_id = {
                    other.id: f
                    for other in activities
                    if (f := next(
                        (r.actual_finish for r in reversed(history.get(other.id, []))
                         if r.actual_finish and r.actual_finish <= cutoff),
                        None,
                    ))
                }
                built = self._build_one(
                    activity, cutoff, preds, succs, history, finish_by_id, by_id
                )
                # Restore the outcome so the row can be labelled, without
                # letting it into the feature vector.
                built.status = ActivityStatus.COMPLETED
                built.actual_finish = actual_finish
                rows_out.append(built)
        return rows_out

    # ------------------------------------------------------------------ core

    def _build_one(
        self,
        activity: Activity,
        as_of: date,
        preds: dict[uuid.UUID, list[uuid.UUID]],
        succs: dict[uuid.UUID, list[uuid.UUID]],
        history: dict[uuid.UUID, list[ActualProgress]],
        finish_by_id: dict[uuid.UUID, date],
        by_id: dict[uuid.UUID, Activity],
    ) -> ActivityFeatures:
        import math

        rows = [r for r in history.get(activity.id, ()) if r.reporting_date <= as_of]
        latest = rows[-1] if rows else None
        notes: list[str] = []

        # --- completion -------------------------------------------------
        budget = activity.budgeted_quantity
        completed = 0.0
        if latest is not None:
            if budget is not None and budget > 0 and latest.actual_quantity is not None:
                completed = max(0.0, min(1.0, latest.actual_quantity / budget))
            elif latest.percent_complete is not None:
                completed = max(0.0, min(1.0, latest.percent_complete / 100.0))
            elif latest.status == ActivityStatus.COMPLETED:
                completed = 1.0

        # --- planned window --------------------------------------------
        start, finish = activity.planned_start, activity.planned_finish
        duration_known = start is not None and finish is not None
        duration = float((finish - start).days) if duration_known else 0.0
        if duration_known and duration <= 0:
            duration = 1.0
            notes.append("planned start and finish are the same day")

        elapsed_fraction = 0.0
        planned_fraction = 0.0
        days_remaining: int | None = None
        if duration_known:
            elapsed = (as_of - start).days
            elapsed_fraction = max(0.0, min(2.0, elapsed / duration))
            planned_fraction = max(0.0, min(1.0, elapsed / duration))
            days_remaining = (finish - as_of).days

        # --- rate analysis ---------------------------------------------
        # Achieved rate is measured over the reported window, not from the
        # planned start: an activity that began late should not be scored as
        # if it had been idling since the plan said it would begin.
        achieved_rate: float | None = None
        if len(rows) >= 2:
            span = (rows[-1].reporting_date - rows[0].reporting_date).days
            if span > 0:
                first = 0.0
                if budget is not None and budget > 0 and rows[0].actual_quantity is not None:
                    first = rows[0].actual_quantity / budget
                elif rows[0].percent_complete is not None:
                    first = rows[0].percent_complete / 100.0
                gained = max(0.0, completed - first)
                achieved_rate = gained / span
        elif len(rows) == 1 and duration_known and completed > 0:
            span = (rows[0].reporting_date - start).days
            if span > 0:
                achieved_rate = completed / span

        required_rate: float | None = None
        if duration_known and days_remaining is not None and days_remaining > 0:
            required_rate = max(0.0, 1.0 - completed) / days_remaining

        rate_ratio = 0.0
        rate_ratio_known = 0.0
        if achieved_rate is not None and required_rate is not None:
            rate_ratio_known = 1.0
            if required_rate <= 0:
                rate_ratio = 2.0  # nothing left to do; cap rather than divide
            else:
                rate_ratio = min(3.0, achieved_rate / required_rate)
        elif achieved_rate is not None and required_rate is None:
            # Past the planned finish with work outstanding: no rate can catch
            # it up, which is a meaningful zero rather than a missing value.
            if completed < 1.0:
                rate_ratio_known = 1.0
                rate_ratio = 0.0
                notes.append("already past the planned finish with work outstanding")

        # --- predecessors ----------------------------------------------
        predecessor_ids = preds.get(activity.id, [])
        slips = [
            (finish_by_id[pid] - by_id[pid].planned_finish).days
            for pid in predecessor_ids
            if pid in finish_by_id
            and pid in by_id
            and by_id[pid].planned_finish is not None
        ]
        max_slip = max(slips) if slips else None
        if max_slip is not None and max_slip > 0:
            notes.append(f"a predecessor finished {max_slip} days late")

        # --- reporting cadence -----------------------------------------
        last_report = rows[-1].reporting_date if rows else None
        gap = (as_of - last_report).days if last_report else 0

        month = finish.month if finish else 1

        values = {
            "planned_duration_days": duration,
            "planned_duration_known": 1.0 if duration_known else 0.0,
            "budgeted_quantity_log": math.log1p(budget) if budget and budget > 0 else 0.0,
            "budgeted_quantity_known": 1.0 if budget and budget > 0 else 0.0,
            "wbs_level": float(activity.level),
            "predecessor_count": float(len(predecessor_ids)),
            "successor_count": float(len(succs.get(activity.id, []))),
            "max_predecessor_slip_days": float(max_slip) if max_slip is not None else 0.0,
            "predecessor_slip_known": 1.0 if max_slip is not None else 0.0,
            "report_count": float(len(rows)),
            "days_since_last_report": float(gap),
            "reporting_gap_known": 1.0 if last_report else 0.0,
            "elapsed_fraction": elapsed_fraction,
            "percent_complete": completed,
            "planned_percent_complete": planned_fraction,
            "progress_deficit": completed - planned_fraction,
            "achieved_rate_per_day": achieved_rate if achieved_rate is not None else 0.0,
            "required_rate_per_day": required_rate if required_rate is not None else 0.0,
            "rate_ratio": rate_ratio,
            "rate_ratio_known": rate_ratio_known,
            "days_remaining": float(days_remaining) if days_remaining is not None else 0.0,
            "is_started": 1.0 if completed > 0 or rows else 0.0,
            "finish_month_sin": math.sin(2 * math.pi * month / 12.0),
            "finish_month_cos": math.cos(2 * math.pi * month / 12.0),
            "is_monsoon_finish": 1.0 if month in _MONSOON_MONTHS else 0.0,
            "discipline_ordinal": float(_discipline_ordinal(activity.discipline)),
        }

        return ActivityFeatures(
            activity_id=activity.id,
            activity_code=activity.activity_code,
            name=activity.name,
            wbs_path=activity.wbs_path,
            values=values,
            as_of=as_of,
            status=latest.status if latest else ActivityStatus.NOT_STARTED,
            planned_start=start,
            planned_finish=finish,
            actual_finish=latest.actual_finish if latest else None,
            budgeted_quantity=budget,
            uom=activity.uom,
            completed_fraction=completed,
            achieved_rate=achieved_rate,
            required_rate=required_rate,
            days_remaining=days_remaining,
            last_report_on=last_report,
            report_count=len(rows),
            max_predecessor_slip=max_slip,
            notes=notes,
        )


def _discipline_ordinal(discipline: str | None) -> int:
    """Stable integer per discipline.

    Ordinal rather than one-hot because tree ensembles split on it perfectly
    well and 11 sparse columns on a training set this small would cost more in
    variance than the encoding buys. ``-1`` marks an unstated discipline, kept
    distinct from ``OTHER``, which is a stated catch-all.
    """
    if not discipline:
        return -1
    try:
        return _DISCIPLINE_ORDER.index(Discipline(discipline))
    except ValueError:
        return len(_DISCIPLINE_ORDER)
