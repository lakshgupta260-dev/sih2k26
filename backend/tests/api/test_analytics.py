"""Planned-vs-actual analytics.

These tests pin the two properties that matter most: the numbers are derived
from the seeded plan and progress (so they can be predicted by hand), and
where the data cannot support a figure the response says null rather than
producing a plausible one.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import JobStatus
from app.models.schedule import Activity, Schedule
from tests.api.test_progress import make_project, progress_url, seed_schedule


@pytest.fixture
def scenario(client: TestClient, auth_headers, manager_user, db: Session):
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "ANLY")
    schedule, parent, small, large = seed_schedule(db, project_id, manager_user.id)
    return {
        "headers": headers, "project_id": project_id, "schedule": schedule,
        "parent": parent, "small": small, "large": large,
    }


def analytics_url(project_id, schedule_id, leaf: str) -> str:
    return (
        f"/api/v1/projects/{project_id}/schedules/{schedule_id}/analytics/{leaf}"
    )


def _report(client, scenario, activity, on: str, quantity: float, finish: str | None = None):
    payload = {"reporting_date": on, "actual_quantity": quantity,
               "status": "COMPLETED" if finish else "IN_PROGRESS"}
    if finish:
        payload["actual_finish"] = finish
    response = client.post(
        progress_url(scenario["project_id"], scenario["schedule"].id, activity.id),
        headers=scenario["headers"], json=payload,
    )
    assert response.status_code == status.HTTP_200_OK, response.text


# -------------------------------------------------------------------- summary

def test_summary_computes_planned_and_actual_against_a_fixed_date(
    client: TestClient, scenario
):
    """Hand-checkable: on 2026-03-01 the 100-unit leaf (Jan 1 - Mar 1) is
    planned 100% done and the 900-unit leaf (Feb 1 - Jun 1) is 28/120 days in.
    Planned overall = (1.0*100 + 0.2333*900) / 1000 = 31.0%.
    We report 50 of the small leaf's 100 units, so actual = 5.0%."""
    _report(client, scenario, scenario["small"], "2026-03-01", 50.0)

    body = client.get(
        analytics_url(scenario["project_id"], scenario["schedule"].id, "summary"),
        headers=scenario["headers"], params={"as_of": "2026-03-01"},
    ).json()

    assert body["as_of"] == "2026-03-01"
    assert body["total_activities"] == 3
    assert body["leaf_activities"] == 2
    assert body["activities_with_progress"] == 1
    assert body["last_reported_on"] == "2026-03-01"
    assert body["overall_completion_percentage"] == pytest.approx(5.0)
    assert body["planned_completion_percentage"] == pytest.approx(31.0, abs=0.5)
    # Behind plan, so negative.
    assert body["schedule_variance"] == pytest.approx(
        body["overall_completion_percentage"] - body["planned_completion_percentage"]
    )
    assert body["schedule_variance"] < 0


def test_variance_is_null_when_the_plan_carries_no_dates(
    client: TestClient, auth_headers, manager_user, db: Session
):
    """Undated plan means there is nothing to be ahead or behind of. Reporting
    0.0 here would be a measurement that was never made."""
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "NODATE")
    schedule = Schedule(project_id=project_id, name="Undated",
                        uploaded_by_id=manager_user.id, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.flush()
    db.add(Activity(schedule_id=schedule.id, activity_code="X1", name="Task",
                    wbs_path="1", level=1, budgeted_quantity=10.0))
    db.commit()

    body = client.get(
        analytics_url(project_id, schedule.id, "summary"), headers=headers
    ).json()
    assert body["planned_completion_percentage"] is None
    assert body["schedule_variance"] is None
    assert body["overall_completion_percentage"] == pytest.approx(0.0)


def test_empty_schedule_reports_zeroes_not_an_error(
    client: TestClient, auth_headers, manager_user, db: Session
):
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "EMPTY")
    schedule = Schedule(project_id=project_id, name="Empty",
                        uploaded_by_id=manager_user.id, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.commit()

    body = client.get(
        analytics_url(project_id, schedule.id, "summary"), headers=headers
    ).json()
    assert body["total_activities"] == 0
    assert body["last_reported_on"] is None
    assert body["schedule_variance"] is None


# -------------------------------------------------------------------- s-curve

def test_s_curve_is_monotonic_and_ends_at_full_plan(client: TestClient, scenario):
    points = client.get(
        analytics_url(scenario["project_id"], scenario["schedule"].id, "s-curve"),
        headers=scenario["headers"],
    ).json()

    assert len(points) > 1
    planned = [p["planned_percentage"] for p in points]
    assert planned == sorted(planned), "cumulative planned must never decrease"
    assert planned[0] == pytest.approx(0.0)
    assert planned[-1] == pytest.approx(100.0)
    assert points[0]["reporting_date"] == "2026-01-01"
    assert points[-1]["reporting_date"] == "2026-06-01"


def test_actual_is_null_outside_the_reported_window(client: TestClient, scenario):
    """Carrying the last reported value forward would draw a flat actual line
    that reads as an observed stall rather than absent data."""
    _report(client, scenario, scenario["small"], "2026-03-01", 50.0)

    points = client.get(
        analytics_url(scenario["project_id"], scenario["schedule"].id, "s-curve"),
        headers=scenario["headers"],
    ).json()

    before = [p for p in points if p["reporting_date"] < "2026-03-01"]
    after = [p for p in points if p["reporting_date"] > "2026-03-01"]
    assert before and after
    assert all(p["actual_percentage"] is None for p in before)
    assert all(p["actual_percentage"] is None for p in after)

    inside = [p for p in points if p["reporting_date"] == "2026-03-01"]
    if inside:
        assert inside[0]["actual_percentage"] == pytest.approx(5.0)


def test_actual_tracks_reported_quantity_within_the_window(
    client: TestClient, scenario
):
    _report(client, scenario, scenario["small"], "2026-01-08", 20.0)
    _report(client, scenario, scenario["large"], "2026-05-07", 450.0)

    points = client.get(
        analytics_url(scenario["project_id"], scenario["schedule"].id, "s-curve"),
        headers=scenario["headers"],
    ).json()
    measured = [p for p in points if p["actual_percentage"] is not None]
    assert measured, "the reported window must produce actual values"
    values = [p["actual_percentage"] for p in measured]
    assert values == sorted(values), "cumulative actual must never decrease"
    # 20/100 + 450/900 of a 1000-unit total = 2.0% + 45.0%
    assert values[-1] == pytest.approx(47.0)


def test_undated_plan_yields_no_curve_rather_than_a_fabricated_one(
    client: TestClient, auth_headers, manager_user, db: Session
):
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "NOCURVE")
    schedule = Schedule(project_id=project_id, name="Undated",
                        uploaded_by_id=manager_user.id, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.flush()
    db.add(Activity(schedule_id=schedule.id, activity_code="X1", name="Task",
                    wbs_path="1", level=1, budgeted_quantity=10.0))
    db.commit()

    points = client.get(
        analytics_url(project_id, schedule.id, "s-curve"), headers=headers
    ).json()
    assert points == []


def test_s_curve_does_not_depend_on_a_hardcoded_year(client: TestClient, scenario, db: Session):
    """Guards against a mocked curve: shifting the plan must shift the output."""
    scenario["small"].planned_start = date(2027, 1, 1)
    scenario["small"].planned_finish = date(2027, 3, 1)
    scenario["large"].planned_start = date(2027, 2, 1)
    scenario["large"].planned_finish = date(2027, 6, 1)
    db.commit()

    points = client.get(
        analytics_url(scenario["project_id"], scenario["schedule"].id, "s-curve"),
        headers=scenario["headers"],
    ).json()
    assert points[0]["reporting_date"].startswith("2027")
    assert points[-1]["reporting_date"] == "2027-06-01"


# ------------------------------------------------------------------- scoping

def test_analytics_are_scoped_to_the_project(client: TestClient, scenario):
    response = client.get(
        analytics_url(scenario["project_id"], uuid.uuid4(), "summary"),
        headers=scenario["headers"],
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_outsider_cannot_read_analytics(
    client: TestClient, auth_headers, supervisor_user, scenario
):
    outsider = auth_headers(supervisor_user)
    for leaf in ("summary", "s-curve"):
        response = client.get(
            analytics_url(scenario["project_id"], scenario["schedule"].id, leaf),
            headers=outsider,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
