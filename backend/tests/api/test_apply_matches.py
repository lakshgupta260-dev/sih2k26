"""The last link: confirmed matches becoming actual progress.

This closes the document -> extract -> match -> progress chain, so the tests
here run the real Phase 5 matcher over a real stored report and then check
what Phase 6 books against the plan -- and, just as importantly, what it
refuses to book.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import EventType
from app.core.constants import MatchStatus
from app.models.matching import ActivityMatch, ExtractedActivity
from app.models.progress import ActualProgress
from app.models.schedule import Activity
from tests.api.test_matching import _seed
from tests.api.test_progress import make_project

REPORT_DATE = date(2026, 3, 12)


@pytest.fixture
def scenario(client: TestClient, auth_headers, manager_user, db: Session):
    headers = auth_headers(manager_user)
    project_id = make_project(client, headers, "APPLY")
    schedule, report = _seed(db, project_id, manager_user.id)
    # Give the report a date so extracted events can be placed in time.
    report.report_date = REPORT_DATE
    db.commit()
    return {"headers": headers, "project_id": project_id,
            "schedule": schedule, "report": report}


def apply_url(project_id, schedule_id) -> str:
    return (
        f"/api/v1/projects/{project_id}/schedules/{schedule_id}"
        f"/progress/apply-matches"
    )


def _run_matching(client: TestClient, scenario) -> dict:
    response = client.post(
        f"/api/v1/projects/{scenario['project_id']}/matching/run",
        json={}, headers=scenario["headers"],
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def test_confirmed_matches_become_dated_progress_records(
    client: TestClient, scenario, db: Session
):
    summary = _run_matching(client, scenario)
    assert summary["auto_matched"] > 0, summary

    response = client.post(
        apply_url(scenario["project_id"], scenario["schedule"].id),
        headers=scenario["headers"],
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()

    assert body["matches_considered"] == summary["auto_matched"]
    assert body["records_created"] == summary["auto_matched"]
    assert body["skipped_missing_event_date"] == 0

    rows = list(db.execute(
        select(ActualProgress)
        .join(Activity, Activity.id == ActualProgress.activity_id)
        .where(Activity.schedule_id == scenario["schedule"].id)
    ).scalars())
    assert len(rows) == body["records_created"]
    assert {r.reporting_date for r in rows} == {REPORT_DATE}
    # Every booked row is traceable back to the report it came from.
    assert all(r.source_report_id == scenario["report"].id for r in rows)


def test_applying_twice_updates_rather_than_duplicating(client: TestClient, scenario):
    _run_matching(client, scenario)
    url = apply_url(scenario["project_id"], scenario["schedule"].id)

    first = client.post(url, headers=scenario["headers"]).json()
    second = client.post(url, headers=scenario["headers"]).json()

    assert first["records_created"] > 0
    assert second["records_created"] == 0
    assert second["records_updated"] == first["records_created"]


def test_percent_from_the_report_lands_on_the_right_activity(
    client: TestClient, scenario, db: Session
):
    """The DPR says G&T at MCC-03 is 60% achieved; that figure must end up on
    A3010 and nowhere else."""
    _run_matching(client, scenario)
    client.post(apply_url(scenario["project_id"], scenario["schedule"].id),
                headers=scenario["headers"])

    row = db.execute(
        select(ActualProgress)
        .join(Activity, Activity.id == ActualProgress.activity_id)
        .where(Activity.activity_code == "A3010",
               Activity.schedule_id == scenario["schedule"].id)
    ).scalar_one_or_none()
    assert row is not None
    assert row.percent_complete == pytest.approx(60.0)


def test_a_confirmed_future_intent_is_still_never_booked(
    client: TestClient, scenario, db: Session
):
    """Defence in depth. The matcher already refuses to link 'to be taken up
    tomorrow', but if a reviewer confirmed such a line by hand it must still
    not become an actual -- booking a stated intention is how a schedule gets
    quietly corrupted."""
    activity = db.execute(
        select(Activity).where(
            Activity.schedule_id == scenario["schedule"].id,
            Activity.activity_code == "A1020",
        )
    ).scalar_one()

    item = ExtractedActivity(
        project_id=scenario["project_id"],
        progress_report_id=scenario["report"].id,
        source_ref="line:99",
        raw_text="L&B 22+500 to 24+000 - to be taken up tomorrow.",
        event_type=EventType.PLANNED_NOT_ACTUAL,
        event_date=REPORT_DATE,
        percent_complete=100.0,
        extractor="test",
    )
    db.add(item)
    db.flush()
    db.add(ActivityMatch(
        project_id=scenario["project_id"],
        extracted_activity_id=item.id,
        activity_id=activity.id,
        status=MatchStatus.MANUALLY_CONFIRMED,
        auto_status=MatchStatus.NEEDS_REVIEW,
        score=0.9,
    ))
    db.commit()

    body = client.post(
        apply_url(scenario["project_id"], scenario["schedule"].id),
        headers=scenario["headers"],
    ).json()
    assert body["skipped_not_an_actual_event"] == 1

    booked = db.execute(
        select(ActualProgress).where(ActualProgress.activity_id == activity.id)
    ).scalar_one_or_none()
    assert booked is None, "a stated intention was booked as actual progress"


def test_an_undated_event_is_skipped_rather_than_dated_to_today(
    client: TestClient, scenario, db: Session
):
    scenario["report"].report_date = None
    db.commit()

    _run_matching(client, scenario)
    body = client.post(
        apply_url(scenario["project_id"], scenario["schedule"].id),
        headers=scenario["headers"],
    ).json()

    assert body["records_created"] == 0
    assert body["skipped_missing_event_date"] == body["matches_considered"]
    assert body["matches_considered"] > 0


def test_matches_still_in_review_are_not_applied(
    client: TestClient, scenario, db: Session
):
    _run_matching(client, scenario)
    pending = db.execute(
        select(ActivityMatch).where(
            ActivityMatch.project_id == scenario["project_id"],
            ActivityMatch.status == MatchStatus.AUTO_MATCHED,
        )
    ).scalars().first()
    assert pending is not None
    pending.status = MatchStatus.NEEDS_REVIEW
    db.commit()

    body = client.post(
        apply_url(scenario["project_id"], scenario["schedule"].id),
        headers=scenario["headers"],
    ).json()
    booked = db.execute(
        select(ActualProgress).where(ActualProgress.activity_id == pending.activity_id)
    ).scalar_one_or_none()
    assert booked is None
    assert body["records_created"] >= 0


def test_the_run_is_audited(client: TestClient, scenario, db: Session):
    from app.models.audit import AuditLog

    _run_matching(client, scenario)
    client.post(apply_url(scenario["project_id"], scenario["schedule"].id),
                headers=scenario["headers"])

    entry = db.execute(
        select(AuditLog).where(AuditLog.action == "PROGRESS_APPLY_MATCHES")
    ).scalar_one()
    assert entry.project_id == scenario["project_id"]
    assert entry.details["records_created"] > 0


def test_outsider_cannot_apply_matches(
    client: TestClient, auth_headers, supervisor_user, scenario
):
    response = client.post(
        apply_url(scenario["project_id"], scenario["schedule"].id),
        headers=auth_headers(supervisor_user),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


def test_unknown_schedule_is_rejected(client: TestClient, scenario):
    response = client.post(
        apply_url(scenario["project_id"], uuid.uuid4()), headers=scenario["headers"]
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
