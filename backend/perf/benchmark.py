"""Measure the read paths that a dashboard hits, against seeded data.

Reports wall-clock time *and* SQL statement count per endpoint. Both matter and
they fail differently: a slow single query is an indexing or query-shape
problem, while a fast-but-numerous pattern is an N+1 that looks fine locally
and collapses the moment the database is a network hop away instead of a unix
socket.

Timing method: each endpoint is called once to warm caches and connection
pools, then measured over several runs, and the **median** is reported. A mean
would be dragged around by the first run's import and pool setup; the median
answers "what does this normally cost".

Usage:
    python -m perf.benchmark                 # seed if needed, then measure
    python -m perf.benchmark --json out.json # machine-readable, for diffing
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any, Callable

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models.project import Project
from app.models.schedule import Schedule
from perf.seed_perf_data import PERF_PROJECT_CODE, seed

RUNS = 5


class QueryCounter:
    """Count SQL statements issued inside the block.

    Hooks the engine rather than the session so it sees statements issued by
    lazy loads too -- which is the entire point when hunting N+1s.
    """

    def __init__(self) -> None:
        self.count = 0
        self.statements: list[str] = []

    def __enter__(self) -> "QueryCounter":
        event.listen(engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, D401
        self.count += 1
        self.statements.append(statement.split("\n")[0][:110])


def _measure(label: str, call: Callable[[], Any]) -> dict[str, Any]:
    """Warm once, then time ``RUNS`` calls and report the median."""
    call()  # warm

    with QueryCounter() as counter:
        call()
    queries = counter.count
    top_statements = counter.statements[:3]

    timings: list[float] = []
    for _ in range(RUNS):
        started = time.perf_counter()
        call()
        timings.append((time.perf_counter() - started) * 1000.0)

    return {
        "label": label,
        "median_ms": round(statistics.median(timings), 1),
        "min_ms": round(min(timings), 1),
        "max_ms": round(max(timings), 1),
        "queries": queries,
        "sample_statements": top_statements,
    }


def _context(db: Session) -> tuple[Project, Schedule]:
    project = db.execute(
        select(Project).where(Project.code == PERF_PROJECT_CODE)
    ).scalar_one_or_none()
    if project is None:
        raise SystemExit(
            "No benchmark data. Run: python -m perf.seed_perf_data"
        )
    schedule = db.execute(
        select(Schedule)
        .where(Schedule.project_id == project.id)
        .order_by(Schedule.created_at.desc())
    ).scalars().first()
    if schedule is None:
        raise SystemExit("Benchmark project has no schedule.")
    return project, schedule


def run() -> list[dict[str, Any]]:
    from app.services.progress import ProgressService
    from app.services.schedule import ScheduleService  # noqa: F401

    db = SessionLocal()
    try:
        project, schedule = _context(db)
        progress = ProgressService(db)

        results = []

        # The rollup is the heaviest read in the product: it walks the whole
        # WBS and needs the current status of every leaf.
        results.append(
            _measure(
                "progress rollup (whole schedule)",
                lambda: (db.expire_all(), progress.get_project_rollup(
                    project, schedule.id
                ))[-1],
            )
        )

        results.append(
            _measure(
                "progress summary",
                lambda: (db.expire_all(), progress.get_summary(
                    project, schedule.id
                ))[-1],
            )
        )

        results.append(
            _measure(
                "S-curve (planned vs actual)",
                lambda: (db.expire_all(), progress.generate_s_curve(
                    project, schedule.id
                ))[-1],
            )
        )

        results.append(
            _measure(
                "latest-progress lookup (internal)",
                lambda: (db.expire_all(), progress._latest_progress(schedule))[-1],
            )
        )

        return results
    finally:
        db.close()


def _user(db: Session):
    from app.models.user import User

    return db.execute(
        select(User).where(User.email == "perf@benchmark.local")
    ).scalar_one()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--seed-if-empty", action="store_true")
    parser.add_argument("--activities", type=int, default=5000)
    parser.add_argument("--reports-per-activity", type=int, default=30)
    args = parser.parse_args()

    if args.seed_if_empty:
        db = SessionLocal()
        try:
            existing = db.execute(
                select(Project).where(Project.code == PERF_PROJECT_CODE)
            ).scalar_one_or_none()
        finally:
            db.close()
        if existing is None:
            seed(args.activities, args.reports_per_activity, quiet=True)

    results = run()

    width = max(len(r["label"]) for r in results) + 2
    print(f"\n{'endpoint'.ljust(width)}{'median':>10}{'min':>9}{'max':>9}{'queries':>10}")
    print("-" * (width + 38))
    for r in results:
        print(
            f"{r['label'].ljust(width)}"
            f"{r['median_ms']:>9.1f}ms"
            f"{r['min_ms']:>8.1f}ms"
            f"{r['max_ms']:>8.1f}ms"
            f"{r['queries']:>10}"
        )
    print()

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
        print(f"wrote {args.json_path}")


if __name__ == "__main__":
    main()
