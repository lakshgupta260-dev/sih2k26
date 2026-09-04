"""Seed a realistically large project for performance measurement.

Oil India's real L1-L6 schedules run to thousands of activities with months of
daily reporting behind them, and every performance claim in
``docs/PERFORMANCE.md`` is measured against data of that shape rather than
against the handful of rows a unit test creates. A query that looks instant
over 20 activities can be the thing that times out over 5,000.

Bulk inserts go through SQLAlchemy Core, not the ORM: seeding 100k progress
rows one mapped object at a time takes minutes and tells us nothing about the
API we are trying to measure.

Usage:
    python -m perf.seed_perf_data --activities 5000 --reports-per-activity 20
"""
from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import insert, select

from app.core.constants import ActivityStatus, JobStatus, UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.progress import ActualProgress
from app.models.project import Project, ProjectMembership
from app.models.schedule import Activity, ActivityDependency, Schedule
from app.models.user import User

# Fixed seed: two runs produce the same dataset, so a before/after comparison
# is measuring the code change and not a different random shape.
random.seed(26122)

PERF_PROJECT_CODE = "PERF-BENCH"
BASELINE_START = date(2026, 1, 1)


def _get_or_create_user(db) -> User:
    user = db.execute(
        select(User).where(User.email == "perf@benchmark.local")
    ).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        email="perf@benchmark.local",
        hashed_password=hash_password("perf-benchmark-password-1"),
        full_name="Perf Benchmark",
        role=UserRole.PROJECT_MANAGER,
    )
    db.add(user)
    db.flush()
    return user


def seed(activities: int, reports_per_activity: int, *, quiet: bool = False) -> dict:
    db = SessionLocal()
    try:
        user = _get_or_create_user(db)

        # Reuse the project across runs so repeated seeding does not pile up
        # unique-constraint violations the way seed_user.py does.
        project = db.execute(
            select(Project).where(Project.code == PERF_PROJECT_CODE)
        ).scalar_one_or_none()
        if project is None:
            project = Project(
                code=PERF_PROJECT_CODE,
                name="Performance Benchmark Project",
                description="Synthetic data for perf measurement. Safe to delete.",
                created_by_id=user.id,
            )
            db.add(project)
            db.flush()
            db.add(
                ProjectMembership(
                    project_id=project.id,
                    user_id=user.id,
                    role=UserRole.PROJECT_MANAGER,
                )
            )
            db.flush()

        schedule = Schedule(
            project_id=project.id,
            name=f"Baseline {activities}x{reports_per_activity}",
            uploaded_by_id=user.id,
            status=JobStatus.COMPLETED,
        )
        db.add(schedule)
        db.flush()

        # A six-level WBS, branching so the tree is wide near the leaves --
        # the shape the rollup actually walks.
        activity_rows: list[dict] = []
        ids_by_level: dict[int, list[uuid.UUID]] = {level: [] for level in range(1, 7)}

        # A real WBS is a pyramid: a handful of L1 packages, thousands of L6
        # work items. An even spread across the six levels would leave only a
        # sixth of the rows as leaves and understate the reporting history that
        # the rollup and S-curve actually have to chew through.
        level_weights = [(1, 1), (2, 2), (3, 5), (4, 10), (5, 22), (6, 60)]
        level_choices = [lvl for lvl, weight in level_weights for _ in range(weight)]

        for index in range(activities):
            # Guarantee at least one activity per level before weighting, so
            # the upper levels always exist to be parents.
            level = index + 1 if index < 6 else random.choice(level_choices)

            parent_id = None
            for candidate_level in range(level - 1, 0, -1):
                if ids_by_level[candidate_level]:
                    parent_id = random.choice(ids_by_level[candidate_level])
                    break

            activity_id = uuid.uuid4()
            ids_by_level[level].append(activity_id)

            start = BASELINE_START + timedelta(days=index % 300)
            activity_rows.append(
                {
                    "id": activity_id,
                    "schedule_id": schedule.id,
                    "activity_code": f"A{index:06d}",
                    "name": f"Activity {index} -- fabrication and erection",
                    "wbs_path": f"1.{'.'.join(str((index >> (3 * d)) % 8) for d in range(level))}",
                    "level": level,
                    "parent_id": parent_id,
                    "planned_start": start,
                    "planned_finish": start + timedelta(days=14),
                    "budgeted_quantity": float(random.randint(10, 5000)),
                    "uom": random.choice(["m", "m3", "t", "nos"]),
                    "discipline": random.choice(["CIVIL", "MECHANICAL", "ELECTRICAL"]),
                }
            )

        db.execute(insert(Activity), activity_rows)
        db.flush()
        if not quiet:
            print(f"  activities:          {len(activity_rows):>8,}")

        # Leaf activities carry the reporting history.
        leaf_ids = ids_by_level[6] or ids_by_level[max(ids_by_level)]
        progress_rows: list[dict] = []
        for leaf_id in leaf_ids:
            pct = 0.0
            for report_index in range(reports_per_activity):
                pct = min(100.0, pct + random.uniform(1.0, 9.0))
                progress_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "activity_id": leaf_id,
                        "reporting_date": BASELINE_START + timedelta(days=report_index * 3),
                        "percent_complete": pct,
                        "actual_quantity": pct * 5,
                        "status": (
                            ActivityStatus.COMPLETED
                            if pct >= 100
                            else ActivityStatus.IN_PROGRESS
                        ),
                        "reported_by_id": user.id,
                    }
                )

        # Chunked so one statement does not carry 100k rows of parameters.
        for start_index in range(0, len(progress_rows), 5000):
            db.execute(insert(ActualProgress), progress_rows[start_index : start_index + 5000])
        db.flush()
        if not quiet:
            print(f"  progress rows:       {len(progress_rows):>8,}")

        # Finish-to-start chain across the leaves, so dependency walks and
        # cycle detection have something real to traverse.
        dependency_rows = [
            {
                "id": uuid.uuid4(),
                "schedule_id": schedule.id,
                "predecessor_id": leaf_ids[i],
                "successor_id": leaf_ids[i + 1],
                "dependency_type": "FS",
                "lag_days": 0.0,
            }
            for i in range(len(leaf_ids) - 1)
        ]
        if dependency_rows:
            db.execute(insert(ActivityDependency), dependency_rows)
        if not quiet:
            print(f"  dependencies:        {len(dependency_rows):>8,}")

        db.commit()
        return {
            "project_id": str(project.id),
            "schedule_id": str(schedule.id),
            "user_email": user.email,
            "activities": len(activity_rows),
            "progress_rows": len(progress_rows),
            "leaves": len(leaf_ids),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activities", type=int, default=5000)
    parser.add_argument("--reports-per-activity", type=int, default=20)
    args = parser.parse_args()

    print(f"Seeding {args.activities:,} activities...")
    result = seed(args.activities, args.reports_per_activity)
    print("\nSeeded:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
