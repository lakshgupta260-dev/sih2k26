"""Rollup traversal against pathological schedules.

These cases are awkward to reach through the API but are exactly the shapes
that hang or silently drop data in a naive recursive rollup, so they get
direct tests.
"""
from __future__ import annotations

import time
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.constants import ActivityStatus, JobStatus
from app.models.progress import ActualProgress
from app.models.project import Project
from app.models.schedule import Activity, Schedule
from app.services.progress import ProgressService, _wbs_sort_key


@pytest.fixture
def project_and_schedule(db: Session, manager_user):
    project = Project(code=f"SVC-{id(db) % 100000}", name="Service test",
                      created_by_id=manager_user.id)
    db.add(project)
    db.flush()
    schedule = Schedule(project_id=project.id, name="Baseline",
                        uploaded_by_id=manager_user.id, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.flush()
    return project, schedule


def test_wbs_sort_key_orders_numerically():
    paths = ["1.10", "1.2", "1.9", "2.1", "1.1"]
    assert sorted(paths, key=_wbs_sort_key) == ["1.1", "1.2", "1.9", "1.10", "2.1"]


def test_wbs_sort_key_tolerates_non_numeric_segments():
    paths = ["1.b", "1.2", "1.a"]
    ordered = sorted(paths, key=_wbs_sort_key)
    assert ordered[0] == "1.2"
    assert ordered[1:] == ["1.a", "1.b"]


def test_parent_cycle_does_not_hang_and_still_reports_every_activity(
    db: Session, project_and_schedule
):
    """A corrupt parent_id cycle must degrade to reporting the nodes as
    leaves, not spin forever in the traversal."""
    project, schedule = project_and_schedule
    a = Activity(schedule_id=schedule.id, activity_code="C1", name="A",
                 wbs_path="1", level=1, budgeted_quantity=10.0)
    b = Activity(schedule_id=schedule.id, activity_code="C2", name="B",
                 wbs_path="1.1", level=2, budgeted_quantity=10.0)
    db.add_all([a, b])
    db.flush()
    a.parent_id = b.id
    b.parent_id = a.id
    db.commit()

    started = time.monotonic()
    rollups = ProgressService(db).get_project_rollup(project, schedule.id)
    assert time.monotonic() - started < 5.0
    assert {r.activity_code for r in rollups} == {"C1", "C2"}


def test_deep_chain_rolls_up_through_every_level(db: Session, project_and_schedule):
    """A six-level chain, which is the deepest the spec allows, must carry the
    leaf's completion all the way to the root."""
    project, schedule = project_and_schedule
    parent_id = None
    leaf = None
    for level in range(1, 7):
        node = Activity(
            schedule_id=schedule.id, activity_code=f"L{level}", name=f"Level {level}",
            wbs_path=".".join(["1"] * level), level=level, parent_id=parent_id,
            budgeted_quantity=50.0 if level == 6 else None,
        )
        db.add(node)
        db.flush()
        parent_id = node.id
        leaf = node
    db.add(ActualProgress(activity_id=leaf.id, reporting_date=date(2026, 3, 1),
                          actual_quantity=25.0, status=ActivityStatus.IN_PROGRESS))
    db.commit()

    rollups = {r.activity_code: r for r in
               ProgressService(db).get_project_rollup(project, schedule.id)}
    assert len(rollups) == 6
    for level in range(1, 7):
        assert rollups[f"L{level}"].completion_percentage == pytest.approx(50.0)
    assert rollups["L6"].is_leaf is True
    assert rollups["L1"].is_leaf is False


def test_wide_schedule_rolls_up_in_a_single_pass(db: Session, project_and_schedule):
    """1,000 leaves under one parent. A rollup that re-walks each subtree per
    activity turns this into a million-step job; one pass keeps it quick."""
    project, schedule = project_and_schedule
    root = Activity(schedule_id=schedule.id, activity_code="R", name="Root",
                    wbs_path="1", level=1)
    db.add(root)
    db.flush()
    db.add_all([
        Activity(schedule_id=schedule.id, activity_code=f"W{i}", name=f"Leaf {i}",
                 wbs_path=f"1.{i}", level=2, parent_id=root.id, budgeted_quantity=1.0)
        for i in range(1000)
    ])
    db.commit()

    started = time.monotonic()
    rollups = ProgressService(db).get_project_rollup(project, schedule.id)
    elapsed = time.monotonic() - started
    assert len(rollups) == 1001
    assert elapsed < 5.0, f"rollup took {elapsed:.1f}s for 1,001 activities"


def test_unbudgeted_siblings_fall_back_to_an_activity_count(
    db: Session, project_and_schedule
):
    """With no budgets anywhere the rollup degrades to counting activities
    rather than dropping them out of the denominator."""
    project, schedule = project_and_schedule
    root = Activity(schedule_id=schedule.id, activity_code="R", name="Root",
                    wbs_path="1", level=1)
    db.add(root)
    db.flush()
    kids = [
        Activity(schedule_id=schedule.id, activity_code=f"K{i}", name=f"Kid {i}",
                 wbs_path=f"1.{i}", level=2, parent_id=root.id)
        for i in range(4)
    ]
    db.add_all(kids)
    db.flush()
    db.add(ActualProgress(activity_id=kids[0].id, reporting_date=date(2026, 3, 1),
                          percent_complete=100.0, status=ActivityStatus.COMPLETED))
    db.commit()

    rollups = {r.activity_code: r for r in
               ProgressService(db).get_project_rollup(project, schedule.id)}
    assert rollups["R"].weight == pytest.approx(4.0)
    assert rollups["R"].completion_percentage == pytest.approx(25.0)


def test_progress_after_the_as_of_date_is_excluded(db: Session, project_and_schedule):
    project, schedule = project_and_schedule
    node = Activity(schedule_id=schedule.id, activity_code="T1", name="Task",
                    wbs_path="1", level=1, budgeted_quantity=100.0)
    db.add(node)
    db.flush()
    db.add_all([
        ActualProgress(activity_id=node.id, reporting_date=date(2026, 3, 1),
                       actual_quantity=30.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=node.id, reporting_date=date(2026, 4, 1),
                       actual_quantity=80.0, status=ActivityStatus.IN_PROGRESS),
    ])
    db.commit()

    service = ProgressService(db)
    early = service.get_project_rollup(project, schedule.id, as_of=date(2026, 3, 15))
    late = service.get_project_rollup(project, schedule.id, as_of=date(2026, 4, 15))
    assert early[0].completion_percentage == pytest.approx(30.0)
    assert late[0].completion_percentage == pytest.approx(80.0)


def test_completion_is_clamped_to_the_budget(db: Session, project_and_schedule):
    """Over-reporting past the budget must not push a parent above 100%."""
    project, schedule = project_and_schedule
    node = Activity(schedule_id=schedule.id, activity_code="T1", name="Task",
                    wbs_path="1", level=1, budgeted_quantity=100.0)
    db.add(node)
    db.flush()
    db.add(ActualProgress(activity_id=node.id, reporting_date=date(2026, 3, 1),
                          actual_quantity=150.0, status=ActivityStatus.IN_PROGRESS))
    db.commit()

    rollups = ProgressService(db).get_project_rollup(project, schedule.id)
    assert rollups[0].completion_percentage == pytest.approx(100.0)
