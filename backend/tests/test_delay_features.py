"""Feature engineering against a real schedule and real progress rows.

The case that matters most here is the leakage guard. A model that can see an
activity's outcome in its own inputs will report a superb ROC AUC and be
useless in production, and that failure is silent -- nothing crashes, the
number just lies. So it gets an explicit test.
"""
from __future__ import annotations

import math
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.constants import ActivityStatus, Discipline, JobStatus
from app.ml.features import FEATURE_NAMES, FeatureBuilder
from app.models.progress import ActualProgress
from app.models.project import Project
from app.models.schedule import Activity, ActivityDependency, Schedule


@pytest.fixture
def schedule(db: Session, manager_user):
    project = Project(code=f"FEAT-{id(db) % 100000}", name="Features",
                      created_by_id=manager_user.id)
    db.add(project)
    db.flush()
    row = Schedule(project_id=project.id, name="Baseline",
                   uploaded_by_id=manager_user.id, status=JobStatus.COMPLETED)
    db.add(row)
    db.flush()
    return row


def _activity(db, schedule, code, **kwargs) -> Activity:
    defaults = dict(
        schedule_id=schedule.id, activity_code=code, name=f"Activity {code}",
        wbs_path=f"1.{code[-1]}", level=6,
    )
    defaults.update(kwargs)
    activity = Activity(**defaults)
    db.add(activity)
    db.flush()
    return activity


def test_every_declared_feature_is_produced(db: Session, schedule):
    _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
              planned_finish=date(2026, 3, 1), budgeted_quantity=100.0)
    db.commit()

    rows = FeatureBuilder(db).build_for_schedule(schedule, as_of=date(2026, 2, 1))
    assert len(rows) == 1
    assert set(rows[0].values) == set(FEATURE_NAMES)
    assert len(rows[0].vector()) == len(FEATURE_NAMES)


def test_only_leaf_activities_are_scored(db: Session, schedule):
    """A parent's progress is an aggregate; forecasting it would be
    forecasting a summary of other forecasts."""
    parent = _activity(db, schedule, "P1", level=1, wbs_path="1")
    _activity(db, schedule, "C1", level=2, wbs_path="1.1", parent_id=parent.id)
    _activity(db, schedule, "C2", level=2, wbs_path="1.2", parent_id=parent.id)
    db.commit()

    rows = FeatureBuilder(db).build_for_schedule(schedule)
    assert {r.activity_code for r in rows} == {"C1", "C2"}


def test_rate_is_measured_over_the_reported_window_not_the_planned_start(
    db: Session, schedule
):
    """An activity that began late should not be scored as though it had been
    idling since the plan said it would start."""
    activity = _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
                         planned_finish=date(2026, 4, 1), budgeted_quantity=100.0)
    db.add_all([
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 3, 1),
                       actual_quantity=10.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 3, 11),
                       actual_quantity=30.0, status=ActivityStatus.IN_PROGRESS),
    ])
    db.commit()

    row = FeatureBuilder(db).build_for_schedule(
        schedule, as_of=date(2026, 3, 11)
    )[0]
    # 20% gained over 10 reported days = 2%/day, not 30% over 70 planned days.
    assert row.achieved_rate == pytest.approx(0.02)
    assert row.completed_fraction == pytest.approx(0.30)


def test_required_rate_and_days_remaining_come_from_the_plan(db: Session, schedule):
    activity = _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
                         planned_finish=date(2026, 4, 1), budgeted_quantity=100.0)
    db.add(ActualProgress(activity_id=activity.id, reporting_date=date(2026, 3, 2),
                          actual_quantity=25.0, status=ActivityStatus.IN_PROGRESS))
    db.commit()

    row = FeatureBuilder(db).build_for_schedule(schedule, as_of=date(2026, 3, 2))[0]
    assert row.days_remaining == 30
    # 75% left over 30 days.
    assert row.required_rate == pytest.approx(0.75 / 30)


def test_unknown_values_are_flagged_rather_than_silently_zero(db: Session, schedule):
    """A plan with no dates and no quantity must be distinguishable from one
    stating zero, or a tree will split on the wrong thing."""
    _activity(db, schedule, "A1")
    db.commit()

    row = FeatureBuilder(db).build_for_schedule(schedule)[0]
    assert row.values["planned_duration_known"] == 0.0
    assert row.values["budgeted_quantity_known"] == 0.0
    assert row.values["reporting_gap_known"] == 0.0
    assert row.values["rate_ratio_known"] == 0.0


def test_predecessor_slip_is_measured_from_the_dependency_graph(
    db: Session, schedule
):
    first = _activity(db, schedule, "A1", planned_finish=date(2026, 2, 1),
                      planned_start=date(2026, 1, 1))
    second = _activity(db, schedule, "A2", planned_start=date(2026, 2, 1),
                       planned_finish=date(2026, 3, 1))
    db.add(ActivityDependency(schedule_id=schedule.id, predecessor_id=first.id,
                              successor_id=second.id))
    db.add(ActualProgress(activity_id=first.id, reporting_date=date(2026, 2, 15),
                          actual_finish=date(2026, 2, 15), percent_complete=100.0,
                          status=ActivityStatus.COMPLETED))
    db.commit()

    rows = {r.activity_code: r for r in
            FeatureBuilder(db).build_for_schedule(schedule, as_of=date(2026, 2, 20))}
    assert rows["A2"].max_predecessor_slip == 14
    assert rows["A2"].values["predecessor_count"] == 1.0
    assert rows["A1"].values["successor_count"] == 1.0
    assert any("predecessor finished 14 days late" in n for n in rows["A2"].notes)


def test_monsoon_and_cyclic_month_encode_the_planned_finish(db: Session, schedule):
    _activity(db, schedule, "A1", planned_start=date(2026, 5, 1),
              planned_finish=date(2026, 7, 15))
    _activity(db, schedule, "A2", planned_start=date(2026, 11, 1),
              planned_finish=date(2026, 12, 15))
    db.commit()

    rows = {r.activity_code: r for r in FeatureBuilder(db).build_for_schedule(schedule)}
    assert rows["A1"].values["is_monsoon_finish"] == 1.0
    assert rows["A2"].values["is_monsoon_finish"] == 0.0
    assert rows["A1"].values["finish_month_sin"] == pytest.approx(
        math.sin(2 * math.pi * 7 / 12)
    )


def test_unstated_discipline_is_distinct_from_the_other_catch_all(
    db: Session, schedule
):
    _activity(db, schedule, "A1", discipline=None)
    _activity(db, schedule, "A2", discipline=Discipline.OTHER)
    db.commit()

    rows = {r.activity_code: r for r in FeatureBuilder(db).build_for_schedule(schedule)}
    assert rows["A1"].values["discipline_ordinal"] == -1.0
    assert rows["A2"].values["discipline_ordinal"] != -1.0


# --------------------------------------------------------------- the label

def test_only_completed_activities_with_both_dates_are_labelled(
    db: Session, schedule
):
    done = _activity(db, schedule, "A1", planned_finish=date(2026, 2, 1),
                     planned_start=date(2026, 1, 1))
    running = _activity(db, schedule, "A2", planned_finish=date(2026, 5, 1),
                        planned_start=date(2026, 1, 1))
    db.add_all([
        ActualProgress(activity_id=done.id, reporting_date=date(2026, 2, 20),
                       actual_finish=date(2026, 2, 20), percent_complete=100.0,
                       status=ActivityStatus.COMPLETED),
        ActualProgress(activity_id=running.id, reporting_date=date(2026, 2, 20),
                       percent_complete=40.0, status=ActivityStatus.IN_PROGRESS),
    ])
    db.commit()

    rows = {r.activity_code: r for r in
            FeatureBuilder(db).build_for_schedule(schedule, as_of=date(2026, 2, 25))}
    assert rows["A1"].finished_late is True
    # An unfinished activity has no truth. Calling it "on time" would teach the
    # model that everything still running is fine.
    assert rows["A2"].finished_late is None


def test_training_rows_are_taken_partway_through_the_planned_window(
    db: Session, schedule
):
    """One row per cutoff, each dated inside the planned window.

    The end of the window is the wrong place to sample even though it looks
    like the safe one: an activity that finishes late is, the day before it
    finishes, already past its planned finish with work outstanding, which
    makes the label readable straight off the features.
    """
    activity = _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
                         planned_finish=date(2026, 3, 1), budgeted_quantity=100.0)
    db.add_all([
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 1, 10),
                       actual_quantity=10.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 2, 10),
                       actual_quantity=40.0, status=ActivityStatus.IN_PROGRESS),
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 4, 15),
                       actual_quantity=100.0, actual_finish=date(2026, 4, 15),
                       status=ActivityStatus.COMPLETED),
    ])
    db.commit()

    builder = FeatureBuilder(db)
    training = builder.build_training_rows(schedule)
    assert len(training) == 3  # 30%, 50% and 70% of the planned window

    for row in training:
        # Every row is labelled from the real outcome...
        assert row.finished_late is True
        assert row.actual_finish == date(2026, 4, 15)
        # ...and dated inside the planned window, well before the finish.
        assert date(2026, 1, 1) < row.as_of < date(2026, 3, 1)
        # ...so the 100% figure reported on the finish date is not visible, and
        # neither is the fact that the planned finish has already passed.
        assert row.completed_fraction < 1.0
        assert row.days_remaining is not None and row.days_remaining > 0

    # All three rows carry the same activity id, so the trainer can fold on it.
    assert {r.activity_id for r in training} == {activity.id}

    snapshot = builder.build_for_schedule(schedule, as_of=date(2026, 5, 1))[0]
    assert snapshot.completed_fraction == pytest.approx(1.0)


def test_a_cutoff_that_would_see_the_finish_is_dropped(db: Session, schedule):
    """An activity that finished early leaves fewer usable cutoffs, rather
    than rows that can read the answer."""
    activity = _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
                         planned_finish=date(2026, 3, 1), budgeted_quantity=100.0)
    db.add_all([
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 1, 5),
                       actual_quantity=50.0, status=ActivityStatus.IN_PROGRESS),
        # Finished at roughly 30% of the planned window.
        ActualProgress(activity_id=activity.id, reporting_date=date(2026, 1, 19),
                       actual_quantity=100.0, actual_finish=date(2026, 1, 19),
                       percent_complete=100.0, status=ActivityStatus.COMPLETED),
    ])
    db.commit()

    training = FeatureBuilder(db).build_training_rows(schedule)
    assert training, "an early finish should still yield at least one row"
    assert all(r.as_of < date(2026, 1, 19) for r in training)
    assert all(r.finished_late is False for r in training)


def test_activities_without_an_actual_finish_produce_no_training_row(
    db: Session, schedule
):
    _activity(db, schedule, "A1", planned_start=date(2026, 1, 1),
              planned_finish=date(2026, 2, 1))
    db.commit()
    assert FeatureBuilder(db).build_training_rows(schedule) == []


def test_an_empty_schedule_produces_no_rows(db: Session, schedule):
    assert FeatureBuilder(db).build_for_schedule(schedule) == []
    assert FeatureBuilder(db).build_training_rows(schedule) == []
