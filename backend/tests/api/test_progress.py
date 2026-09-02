"""Progress recording, rollup and tenancy isolation, through the real API."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import JobStatus
from app.models.schedule import Activity, Schedule


def make_project(client: TestClient, headers: dict[str, str], label: str) -> uuid.UUID:
    """Create a project through the API so the creator gets a real membership."""
    response = client.post(
        "/api/v1/projects",
        json={"code": f"{label}-{uuid.uuid4().hex[:6]}", "name": f"{label} project"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def seed_schedule(db: Session, project_id: uuid.UUID, user_id: uuid.UUID):
    """A two-level WBS: one parent over two leaves of unequal budget.

    The unequal budgets are the point -- they are what makes a weighted
    rollup distinguishable from an unweighted average.
    """
    schedule = Schedule(
        project_id=project_id, name="Baseline", uploaded_by_id=user_id,
        status=JobStatus.COMPLETED,
    )
    db.add(schedule)
    db.flush()

    parent = Activity(
        schedule_id=schedule.id, activity_code="A100", name="Mainline pipeline",
        wbs_path="1", level=1,
    )
    db.add(parent)
    db.flush()

    small = Activity(
        schedule_id=schedule.id, activity_code="A110", name="Survey and staking",
        wbs_path="1.1", level=2, parent_id=parent.id, budgeted_quantity=100.0,
        uom="m", planned_start=date(2026, 1, 1), planned_finish=date(2026, 3, 1),
    )
    large = Activity(
        schedule_id=schedule.id, activity_code="A120", name="Trenching and lowering",
        wbs_path="1.2", level=2, parent_id=parent.id, budgeted_quantity=900.0,
        uom="m", planned_start=date(2026, 2, 1), planned_finish=date(2026, 6, 1),
    )
    db.add_all([small, large])
    db.commit()
    return schedule, parent, small, large


@pytest.fixture
def scenario(client: TestClient, auth_headers, manager_user, db: Session):
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "PROG")
    schedule, parent, small, large = seed_schedule(db, project_id, manager_user.id)
    return {
        "headers": headers, "project_id": project_id, "schedule": schedule,
        "parent": parent, "small": small, "large": large,
    }


def progress_url(project_id, schedule_id, activity_id) -> str:
    return (
        f"/api/v1/projects/{project_id}/schedules/{schedule_id}"
        f"/activities/{activity_id}/progress"
    )


def rollup_url(project_id, schedule_id) -> str:
    return f"/api/v1/projects/{project_id}/schedules/{schedule_id}/progress/rollup"


# --------------------------------------------------------------------- writes

def test_records_and_reads_back_progress(client: TestClient, scenario):
    url = progress_url(scenario["project_id"], scenario["schedule"].id,
                       scenario["small"].id)
    response = client.post(url, headers=scenario["headers"], json={
        "reporting_date": "2026-02-15", "actual_quantity": 25.0,
        "status": "IN_PROGRESS", "notes": "Staking started at KP 0+000",
    })
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["actual_quantity"] == 25.0
    assert body["status"] == "IN_PROGRESS"

    history = client.get(url, headers=scenario["headers"])
    assert history.status_code == status.HTTP_200_OK
    assert len(history.json()) == 1


def test_reposting_a_date_corrects_it_rather_than_duplicating(
    client: TestClient, scenario
):
    """One row per activity per date, so a restated DPR figure corrects the day."""
    url = progress_url(scenario["project_id"], scenario["schedule"].id,
                       scenario["small"].id)
    for quantity in (25.0, 40.0):
        response = client.post(url, headers=scenario["headers"], json={
            "reporting_date": "2026-02-15", "actual_quantity": quantity,
            "status": "IN_PROGRESS",
        })
        assert response.status_code == status.HTTP_200_OK, response.text

    history = client.get(url, headers=scenario["headers"]).json()
    assert len(history) == 1
    assert history[0]["actual_quantity"] == 40.0


def test_correction_keeps_the_superseded_value_in_the_audit_trail(
    client: TestClient, scenario, db: Session
):
    from sqlalchemy import select

    from app.models.audit import AuditLog

    url = progress_url(scenario["project_id"], scenario["schedule"].id,
                       scenario["small"].id)
    client.post(url, headers=scenario["headers"], json={
        "reporting_date": "2026-02-15", "actual_quantity": 25.0, "status": "IN_PROGRESS",
    })
    client.post(url, headers=scenario["headers"], json={
        "reporting_date": "2026-02-15", "actual_quantity": 40.0, "status": "IN_PROGRESS",
    })

    entries = list(db.execute(
        select(AuditLog).where(AuditLog.entity_type == "actual_progress")
    ).scalars())
    assert len(entries) == 2
    updates = [e for e in entries if e.action == "UPDATE"]
    assert len(updates) == 1
    assert updates[0].details["previous"]["actual_quantity"] == 25.0


def test_actuals_cannot_be_dated_after_the_reporting_date(client: TestClient, scenario):
    """A finish date after the reporting date would book work not yet reported."""
    url = progress_url(scenario["project_id"], scenario["schedule"].id,
                       scenario["small"].id)
    response = client.post(url, headers=scenario["headers"], json={
        "reporting_date": "2026-02-15", "actual_finish": "2026-03-20",
        "status": "COMPLETED",
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text


# --------------------------------------------------------------------- rollup

def test_rollup_is_weighted_by_budgeted_quantity(client: TestClient, scenario):
    """100-unit leaf at 100% and 900-unit leaf at 0% must roll up to 10%,
    not the 50% an unweighted average of the two children would give."""
    headers = scenario["headers"]
    client.post(
        progress_url(scenario["project_id"], scenario["schedule"].id,
                     scenario["small"].id),
        headers=headers,
        json={"reporting_date": "2026-02-15", "actual_quantity": 100.0,
              "status": "COMPLETED", "actual_finish": "2026-02-15"},
    )
    rollups = client.get(
        rollup_url(scenario["project_id"], scenario["schedule"].id), headers=headers
    ).json()
    by_code = {r["activity_code"]: r for r in rollups}

    assert by_code["A110"]["completion_percentage"] == pytest.approx(100.0)
    assert by_code["A120"]["completion_percentage"] == pytest.approx(0.0)
    assert by_code["A100"]["completion_percentage"] == pytest.approx(10.0)
    assert by_code["A100"]["weight"] == pytest.approx(1000.0)
    assert by_code["A100"]["is_leaf"] is False
    assert by_code["A110"]["is_leaf"] is True


def test_reported_quantity_of_zero_is_a_measurement_not_a_blank(
    client: TestClient, scenario
):
    """A reported zero must not fall through to the percentage field."""
    headers = scenario["headers"]
    client.post(
        progress_url(scenario["project_id"], scenario["schedule"].id,
                     scenario["small"].id),
        headers=headers,
        json={"reporting_date": "2026-02-15", "actual_quantity": 0.0,
              "percent_complete": 80.0, "status": "IN_PROGRESS"},
    )
    rollups = client.get(
        rollup_url(scenario["project_id"], scenario["schedule"].id), headers=headers
    ).json()
    by_code = {r["activity_code"]: r for r in rollups}
    assert by_code["A110"]["completion_percentage"] == pytest.approx(0.0)


def test_rollup_orders_wbs_paths_numerically(client: TestClient, scenario, db: Session):
    """1.9 must precede 1.10; plain string ordering gets this wrong."""
    schedule, parent = scenario["schedule"], scenario["parent"]
    for index in (9, 10):
        db.add(Activity(
            schedule_id=schedule.id, activity_code=f"A1{index}0",
            name=f"Section {index}", wbs_path=f"1.{index}", level=2,
            parent_id=parent.id, budgeted_quantity=10.0,
        ))
    db.commit()

    rollups = client.get(
        rollup_url(scenario["project_id"], schedule.id), headers=scenario["headers"]
    ).json()
    paths = [r["wbs_path"] for r in rollups]
    assert paths.index("1.9") < paths.index("1.10")


def test_delay_is_flagged_from_the_planned_finish(client: TestClient, scenario):
    headers = scenario["headers"]
    # Finished a month after the planned finish of 2026-03-01.
    client.post(
        progress_url(scenario["project_id"], scenario["schedule"].id,
                     scenario["small"].id),
        headers=headers,
        json={"reporting_date": "2026-04-01", "actual_finish": "2026-04-01",
              "actual_quantity": 100.0, "status": "COMPLETED"},
    )
    rollups = client.get(
        rollup_url(scenario["project_id"], scenario["schedule"].id), headers=headers
    ).json()
    by_code = {r["activity_code"]: r for r in rollups}
    assert by_code["A110"]["is_delayed"] is True
    # A delayed leaf makes its parent delayed.
    assert by_code["A100"]["is_delayed"] is True


# ------------------------------------------------------------------- scoping

def test_unknown_schedule_is_404_not_an_empty_rollup(client: TestClient, scenario):
    response = client.get(
        rollup_url(scenario["project_id"], uuid.uuid4()), headers=scenario["headers"]
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_schedule_from_another_project_is_not_reachable(
    client: TestClient, scenario, manager_user, db: Session
):
    """Pairing a foreign schedule id with a project the caller does own must
    not leak the foreign schedule."""
    other_project = make_project(client, scenario["headers"], "OTHER")
    foreign_schedule, *_ = seed_schedule(db, other_project, manager_user.id)

    response = client.get(
        rollup_url(scenario["project_id"], foreign_schedule.id),
        headers=scenario["headers"],
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_activity_from_another_schedule_is_not_reachable(
    client: TestClient, scenario, manager_user, db: Session
):
    other_project = make_project(client, scenario["headers"], "OTHER2")
    _, _, foreign_activity, _ = seed_schedule(db, other_project, manager_user.id)

    response = client.post(
        progress_url(scenario["project_id"], scenario["schedule"].id,
                     foreign_activity.id),
        headers=scenario["headers"],
        json={"reporting_date": "2026-02-15", "percent_complete": 50.0},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_outsider_cannot_read_or_write_progress(
    client: TestClient, auth_headers, supervisor_user, scenario
):
    """A user with no membership at all sees 404 on both read and write."""
    outsider = auth_headers(supervisor_user)
    project_id, schedule = scenario["project_id"], scenario["schedule"]

    read = client.get(rollup_url(project_id, schedule.id), headers=outsider)
    assert read.status_code == status.HTTP_404_NOT_FOUND, read.text

    write = client.post(
        progress_url(project_id, schedule.id, scenario["small"].id),
        headers=outsider,
        json={"reporting_date": "2026-02-15", "percent_complete": 50.0},
    )
    assert write.status_code == status.HTTP_404_NOT_FOUND, write.text


def test_anonymous_access_is_rejected(anon_client: TestClient, scenario):
    response = anon_client.get(
        rollup_url(scenario["project_id"], scenario["schedule"].id)
    )
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
    )
