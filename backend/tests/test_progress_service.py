import pytest
import uuid
from datetime import date
from app.models.schedule import Schedule, Activity
from app.models.progress import ActualProgress
from app.services.progress import ProgressService
from app.core.constants import ActivityStatus, JobStatus
from app.models.project import Project

def test_rollup_logic(db, manager_user):
    p = Project(code="TEST-RP", name="Test", created_by_id=manager_user.id)
    db.add(p)
    db.commit()

    schedule = Schedule(
        project_id=p.id,
        name="Rollup Test",
        uploaded_by_id=manager_user.id,
        status=JobStatus.COMPLETED
    )
    db.add(schedule)
    db.flush()

    # L1
    act_l1 = Activity(
        schedule_id=schedule.id, activity_code="L1", name="L1", wbs_path="1", level=1
    )
    db.add(act_l1)
    db.flush()

    # L2.1 (Weight 100)
    act_l2_1 = Activity(
        schedule_id=schedule.id, activity_code="L2.1", name="L2.1", wbs_path="1.1", level=2, parent_id=act_l1.id, budgeted_quantity=100.0
    )
    # L2.2 (Weight 200)
    act_l2_2 = Activity(
        schedule_id=schedule.id, activity_code="L2.2", name="L2.2", wbs_path="1.2", level=2, parent_id=act_l1.id, budgeted_quantity=200.0
    )
    db.add_all([act_l2_1, act_l2_2])
    db.flush()

    # Progress: L2.1 is 50% complete (50/100)
    db.add(ActualProgress(
        activity_id=act_l2_1.id, reporting_date=date(2026, 9, 1), actual_quantity=50.0, status=ActivityStatus.IN_PROGRESS
    ))
    # Progress: L2.2 is 25% complete (50/200)
    db.add(ActualProgress(
        activity_id=act_l2_2.id, reporting_date=date(2026, 9, 1), actual_quantity=50.0, status=ActivityStatus.IN_PROGRESS
    ))
    db.commit()

    service = ProgressService(db)
    rollups = service.get_project_rollup(schedule.id)
    
    rollup_map = {r.activity_code: r for r in rollups}
    assert rollup_map["L2.1"].completion_percentage == 50.0
    assert rollup_map["L2.2"].completion_percentage == 25.0
    
    # L1 should be weighted average: (50*100 + 25*200) / 300 = (5000 + 5000) / 300 = 10000 / 300 = 33.333%
    assert round(rollup_map["L1"].completion_percentage, 1) == 33.3
