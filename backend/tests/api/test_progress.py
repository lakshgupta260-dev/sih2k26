import pytest
import uuid
from datetime import date
from sqlalchemy.orm import Session
from fastapi import status
from fastapi.testclient import TestClient

from app.models.schedule import Activity, Schedule
from app.models.progress import ActualProgress
from app.core.constants import ActivityStatus, JobStatus, Discipline
from app.models.project import Project

@pytest.fixture
def dummy_project(db: Session, manager_user):
    p = Project(code="TEST-PROG", name="Prog Project", created_by_id=manager_user.id)
    db.add(p)
    db.commit()
    return p

@pytest.fixture
def dummy_schedule_and_activities(db: Session, dummy_project, manager_user):
    schedule = Schedule(
        project_id=dummy_project.id,
        name="Test Schedule",
        uploaded_by_id=manager_user.id,
        status=JobStatus.COMPLETED
    )
    db.add(schedule)
    db.flush()

    act_l1 = Activity(
        schedule_id=schedule.id,
        activity_code="A100",
        name="Project L1",
        wbs_path="1",
        level=1,
        budgeted_quantity=100.0
    )
    db.add(act_l1)
    db.flush()

    act_l2 = Activity(
        schedule_id=schedule.id,
        activity_code="A110",
        name="Task L2",
        wbs_path="1.1",
        level=2,
        parent_id=act_l1.id,
        budgeted_quantity=100.0,
        planned_finish=date(2026, 10, 1)
    )
    db.add(act_l2)
    db.flush()
    db.commit()
    
    return schedule, act_l1, act_l2

def test_record_progress(client: TestClient, auth_headers, manager_user, dummy_schedule_and_activities, db: Session):
    schedule, l1, l2 = dummy_schedule_and_activities
    headers = auth_headers(manager_user)
    
    payload = {
        "reporting_date": "2026-09-01",
        "actual_quantity": 25.0,
        "status": "IN_PROGRESS",
        "notes": "Started work"
    }
    
    res = client.post(
        f"/api/v1/projects/{schedule.project_id}/schedules/{schedule.id}/activities/{l2.id}/progress",
        headers=headers,
        json=payload
    )
    
    if res.status_code != 200:
        print("ERROR JSON:", res.json())
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["actual_quantity"] == 25.0
    assert data["status"] == "IN_PROGRESS"
    
    # Check history
    res = client.get(
        f"/api/v1/projects/{schedule.project_id}/schedules/{schedule.id}/activities/{l2.id}/progress",
        headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) == 1
    
    # Rollup
    res = client.get(
        f"/api/v1/projects/{schedule.project_id}/schedules/{schedule.id}/progress/rollup",
        headers=headers
    )
    assert res.status_code == status.HTTP_200_OK
    rollups = res.json()
    assert len(rollups) == 2
    
    l2_rollup = next(r for r in rollups if r["activity_id"] == str(l2.id))
    assert l2_rollup["completion_percentage"] == 25.0
