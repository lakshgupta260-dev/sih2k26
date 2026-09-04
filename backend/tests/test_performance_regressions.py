"""Lock in the Phase 11 query-shape fixes.

These are not timing tests. A wall-clock assertion in CI is a flaky test: it
fails on a loaded runner and passes on a quiet one, and the usual response is
to loosen the threshold until it never fails and never catches anything.

Instead each test asserts the *property* that made the code fast -- the number
of rows the database returns, the number of statements issued -- which is
deterministic, meaningful on a 20-row fixture, and fails loudly if someone
reintroduces the original shape. The measured timings live in
``docs/PERFORMANCE.md`` alongside the dataset they were taken on.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.core.constants import ActivityStatus, JobStatus
from app.models.progress import ActualProgress
from app.models.schedule import Activity, Schedule
from app.services.progress import ProgressService


class _StatementCounter:
    """Count SQL statements, and capture them for assertions on shape."""

    def __init__(self, session: Session) -> None:
        self._bind = session.get_bind()
        self.statements: list[str] = []

    def __enter__(self) -> "_StatementCounter":
        event.listen(self._bind, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self._bind, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        self.statements.append(" ".join(statement.split()))

    @property
    def count(self) -> int:
        return len(self.statements)


@pytest.fixture
def schedule_with_history(db: Session, manager_user, test_project):
    """One schedule, 6 leaves, 12 reports each: 72 progress rows for 6 answers.

    Small enough to be a unit test, and still wide enough that "one row per
    activity" and "every row in the history" are different numbers -- which is
    the entire distinction under test.
    """
    project_id = uuid.UUID(test_project[0])
    schedule = Schedule(
        project_id=project_id,
        name="Perf regression baseline",
        uploaded_by_id=manager_user.id,
        status=JobStatus.COMPLETED,
    )
    db.add(schedule)
    db.flush()

    start = date(2026, 1, 1)
    leaves = []
    for index in range(6):
        activity = Activity(
            schedule_id=schedule.id,
            activity_code=f"L{index}",
            name=f"Leaf {index}",
            wbs_path=f"1.{index}",
            level=6,
            budgeted_quantity=100.0,
            uom="m",
            planned_start=start,
            planned_finish=start + timedelta(days=30),
        )
        db.add(activity)
        db.flush()
        leaves.append(activity)

        for report in range(12):
            db.add(
                ActualProgress(
                    activity_id=activity.id,
                    reporting_date=start + timedelta(days=report * 2),
                    percent_complete=float((report + 1) * 8),
                    actual_quantity=float((report + 1) * 8),
                    status=ActivityStatus.IN_PROGRESS,
                    reported_by_id=manager_user.id,
                )
            )
    db.commit()
    return schedule, leaves


def test_latest_progress_returns_one_row_per_activity_not_the_whole_history(
    db: Session, schedule_with_history
) -> None:
    """The regression this guards: 91,470 rows fetched to produce 3,049 values.

    The original implementation selected every progress row and reduced them in
    Python, so its cost grew with reporting history rather than with the number
    of activities -- fast in a demo, slower every day a project ran. The fix
    pushes the reduction into PostgreSQL with DISTINCT ON.
    """
    schedule, leaves = schedule_with_history

    total_history = db.scalar(
        select(func.count())
        .select_from(ActualProgress)
        .join(Activity, Activity.id == ActualProgress.activity_id)
        .where(Activity.schedule_id == schedule.id)
    )
    assert total_history == 72, "fixture changed; the premise of this test is 72 > 6"

    service = ProgressService(db)
    with _StatementCounter(db) as counter:
        latest = service._latest_progress(schedule)

    assert len(latest) == len(leaves) == 6

    # One statement, and it must be the DISTINCT ON form. Without this
    # assertion the test would still pass if someone reverted to fetching
    # everything and reducing in Python, because the return value is identical.
    assert counter.count == 1, counter.statements
    statement = counter.statements[0].upper()
    assert "DISTINCT ON" in statement, (
        "latest-progress no longer uses DISTINCT ON; it is probably fetching "
        "the full history again -- see docs/PERFORMANCE.md"
    )


def test_latest_progress_picks_the_newest_row(db: Session, schedule_with_history) -> None:
    """DISTINCT ON must order DESC, or it returns the *oldest* report.

    This is the way the optimisation could silently produce wrong answers: the
    query shape is right, the row count is right, and every progress figure is
    stale.
    """
    schedule, leaves = schedule_with_history
    latest = ProgressService(db)._latest_progress(schedule)

    for leaf in leaves:
        row = latest[leaf.id]
        assert row.reporting_date == date(2026, 1, 23), row.reporting_date
        assert row.percent_complete == pytest.approx(96.0)


def test_latest_progress_respects_as_of(db: Session, schedule_with_history) -> None:
    schedule, leaves = schedule_with_history
    latest = ProgressService(db)._latest_progress(schedule, as_of=date(2026, 1, 10))

    for leaf in leaves:
        assert latest[leaf.id].reporting_date <= date(2026, 1, 10)
        # 1 Jan + 2*5 days = 11 Jan is past the cutoff, so the 9 Jan row wins.
        assert latest[leaf.id].reporting_date == date(2026, 1, 9)


def test_s_curve_issues_a_bounded_number_of_queries(
    db: Session, schedule_with_history, test_project
) -> None:
    """The curve must not query per sample point or per activity.

    Its cost should track the size of the schedule, not the number of samples
    on the chart.
    """
    from app.models.project import Project

    schedule, _ = schedule_with_history
    project = db.get(Project, uuid.UUID(test_project[0]))

    service = ProgressService(db)
    with _StatementCounter(db) as counter:
        points = service.generate_s_curve(project, schedule.id)

    assert len(points) > 1
    assert counter.count <= 6, (
        f"S-curve issued {counter.count} statements; it should be a small "
        f"fixed number regardless of sample count: {counter.statements}"
    )


def test_s_curve_does_not_hydrate_orm_entities_for_progress(
    db: Session, schedule_with_history, test_project
) -> None:
    """The progress read must stay a column select.

    Profiling attributed 3.34s of a 5.24s call to ORM hydration of progress
    rows, 1.37s of it parsing three UUIDs per row when the curve reads one.
    Selecting columns removed that. A future refactor that innocently changes
    this back to ``select(ActualProgress)`` would restore the cost with no
    visible change in behaviour, so it is asserted here.
    """
    from app.models.project import Project

    schedule, _ = schedule_with_history
    project = db.get(Project, uuid.UUID(test_project[0]))

    with _StatementCounter(db) as counter:
        ProgressService(db).generate_s_curve(project, schedule.id)

    progress_selects = [
        s for s in counter.statements if "FROM actual_progress" in s.replace('"', "")
    ]
    assert progress_selects, counter.statements

    for statement in progress_selects:
        normalised = statement.replace('"', "").lower()
        # The identity column is the tell: an entity load always selects it,
        # a targeted column select of the five fields the curve needs does not.
        assert "actual_progress.id" not in normalised, (
            "S-curve is loading full ActualProgress entities again -- "
            "see docs/PERFORMANCE.md"
        )


def test_s_curve_actual_is_none_outside_the_reported_window(
    db: Session, schedule_with_history, test_project
) -> None:
    """Behaviour preserved through the rewrite.

    Beyond the last report nothing has been measured, and carrying the last
    value forward would draw a flat line that reads as an observed stall rather
    than absent data.
    """
    from app.models.project import Project

    schedule, _ = schedule_with_history
    project = db.get(Project, uuid.UUID(test_project[0]))

    points = ProgressService(db).generate_s_curve(project, schedule.id)
    last_report = date(2026, 1, 23)

    for point in points:
        if point.reporting_date > last_report:
            assert point.actual_percentage is None, point
        elif point.reporting_date >= date(2026, 1, 1):
            assert point.actual_percentage is not None, point


def test_s_curve_actual_is_monotonic_over_a_monotonic_history(
    db: Session, schedule_with_history, test_project
) -> None:
    """Catches a broken incremental total.

    The optimised loop maintains a running earned figure and adjusts it by the
    delta when an activity reports again. If that bookkeeping were wrong -- for
    instance adding the new contribution without subtracting the old -- the
    curve would climb faster than reality, which this fixture's steadily
    increasing history would expose as a non-monotonic or >100% series.
    """
    from app.models.project import Project

    schedule, _ = schedule_with_history
    project = db.get(Project, uuid.UUID(test_project[0]))

    actuals = [
        p.actual_percentage
        for p in ProgressService(db).generate_s_curve(project, schedule.id)
        if p.actual_percentage is not None
    ]

    assert actuals == sorted(actuals), actuals
    assert all(0.0 <= value <= 100.0 for value in actuals), actuals


def test_audit_foreign_keys_to_users_are_indexed(db: Session) -> None:
    """Every FK to ``users`` must have an index backing it.

    ON DELETE SET NULL makes PostgreSQL scan each child table when a user is
    removed; unindexed, that scan grows with the table. This asserts the
    property rather than the six index names, so a new audit column added in a
    later phase is caught too.
    """
    rows = db.execute(
        text(
            """
            SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
            FROM pg_constraint c
            JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = k.attnum
            WHERE c.contype = 'f'
              AND c.confrelid = 'users'::regclass
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid AND i.indkey[0] = k.attnum
              )
            """
        )
    ).all()

    assert rows == [], f"unindexed foreign keys to users: {rows}"
