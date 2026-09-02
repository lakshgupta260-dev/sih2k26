"""Matching run, review queue, human decisions and tenancy isolation."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import DocumentType, MatchStatus, UserRole
from app.models.document import ProgressReport, UploadedFile
from app.models.schedule import Activity, Schedule

DPR_TEXT = """
A. WORK EXECUTED TODAY
  1. L&B done from 12.0 to 14.5 km completed. Total 2500 m.
  2. RT of jt 340-380 completed, 2 repairs.
  3. G&T at MCC-03 in progress - 60% achieved cumulative.
  4. fdn concreting M-30 for Pump Shed commenced today.
  5. Toolbox talk conducted on working at height.
C. PLANNED FOR TOMORROW
  - L&B 22+500 to 24+000 - to be taken up tomorrow.
"""

PLAN_ROWS = [
    ("A1010", "Pipe Lowering and Backfilling KP 12.000 - 14.500", "1.1.1.1", 6, "PIPING"),
    ("A1020", "Pipe Lowering and Backfilling KP 22.500 - 24.000", "1.1.1.2", 6, "PIPING"),
    ("A2010", "Radiographic Testing of Girth Joints J-0340 to J-0380", "1.2.1.1", 6, "WELDING_NDT"),
    ("A3010", "Cable Glanding and Termination at MCC-03", "2.1.1.1", 6, "ELECTRICAL"),
    ("A4010", "Foundation Concreting M30 Pump Shed", "2.2.1.1", 6, "CIVIL"),
]


def _seed(db: Session, project_id: uuid.UUID, user_id: uuid.UUID, text: str = DPR_TEXT):
    """Create a schedule with activities plus one stored progress report."""
    schedule = Schedule(project_id=project_id, name="Baseline", uploaded_by_id=user_id)
    db.add(schedule)
    db.flush()
    for code, name, wbs, level, discipline in PLAN_ROWS:
        db.add(
            Activity(
                schedule_id=schedule.id, activity_code=code, name=name,
                wbs_path=wbs, level=level, discipline=discipline,
            )
        )
    upload = UploadedFile(
        project_id=project_id, uploaded_by_id=user_id,
        original_filename="dpr.txt", storage_path=f"{project_id}/{uuid.uuid4().hex}.txt",
        content_type="text/plain", size_bytes=len(text), sha256=uuid.uuid4().hex * 2,
        document_type=DocumentType.DAILY_PROGRESS_REPORT,
    )
    db.add(upload)
    db.flush()
    report = ProgressReport(
        project_id=project_id, uploaded_file_id=upload.id, raw_text=text, extracted_data={}
    )
    db.add(report)
    db.flush()
    return schedule, report


@pytest.fixture
def project(client: TestClient, manager_user, auth_headers, db: Session):
    headers = auth_headers(manager_user)
    response = client.post(
        "/api/v1/projects",
        json={"code": f"MATCH-{uuid.uuid4().hex[:6]}", "name": "Matching Test"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    project_id = uuid.UUID(response.json()["id"])
    schedule, report = _seed(db, project_id, manager_user.id)
    return project_id, headers, schedule, report


def _base(project_id: uuid.UUID) -> str:
    return f"/api/v1/projects/{project_id}/matching"


# ------------------------------------------------------------------------ run
def test_run_extracts_matches_and_reports_provenance(client: TestClient, project) -> None:
    project_id, headers, schedule, _ = project
    response = client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["reports_processed"] == 1
    assert body["items_extracted"] >= 6
    assert body["matches_created"] == body["items_extracted"]
    assert body["auto_matched"] >= 3
    assert body["schedule_id"] == str(schedule.id)
    # The response must be unambiguous about how the result was produced.
    assert body["extractors_used"] == ["rule_based"]
    assert body["embedding_provider"] == "tfidf"
    assert body["llm_available"] is False


def test_shorthand_lines_link_to_the_right_activities(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)

    rows = client.get(
        f"{_base(project_id)}/matches", params={"limit": 100}, headers=headers
    ).json()["items"]

    def linked_code_for(fragment: str) -> str | None:
        """The activity code linked to the line containing this fragment."""
        for row in rows:
            if fragment.lower() in row["extracted"]["raw_text"].lower():
                if not row["activity_id"]:
                    return None
                return row["candidates"][0]["activity_code"]
        pytest.fail(f"no extracted line contained {fragment!r}")

    # Each of these is field shorthand that shares almost no characters with
    # the plan wording it must resolve to.
    assert linked_code_for("L&B done from 12.0") == "A1010"
    assert linked_code_for("RT of jt 340-380") == "A2010"
    assert linked_code_for("G&T at MCC-03") == "A3010"
    assert linked_code_for("fdn concreting") == "A4010"


def test_future_intent_and_non_events_are_never_linked(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    rows = client.get(
        f"{_base(project_id)}/matches", params={"limit": 100}, headers=headers
    ).json()["items"]

    for row in rows:
        text = row["extracted"]["raw_text"].lower()
        if "to be taken up" in text or "toolbox" in text:
            assert row["activity_id"] is None, text
            assert row["status"] == MatchStatus.UNMATCHED


def test_rerun_does_not_duplicate_and_reprocess_replaces(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    first = client.post(f"{_base(project_id)}/run", json={}, headers=headers).json()

    again = client.post(f"{_base(project_id)}/run", json={}, headers=headers).json()
    assert again["reports_processed"] == 0, "already-processed reports must be skipped"

    forced = client.post(
        f"{_base(project_id)}/run", json={"reprocess": True}, headers=headers
    ).json()
    assert forced["items_extracted"] == first["items_extracted"]

    total = client.get(
        f"{_base(project_id)}/extracted", params={"limit": 200}, headers=headers
    ).json()["total"]
    assert total == first["items_extracted"], "reprocess must replace, not append"


def test_thresholds_can_be_overridden_per_run(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    strict = client.post(
        f"{_base(project_id)}/run",
        json={"auto_threshold": 0.999, "review_threshold": 0.998, "reprocess": True},
        headers=headers,
    ).json()
    assert strict["auto_matched"] == 0
    assert strict["auto_threshold"] == 0.999


def test_run_rejects_inverted_thresholds(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    response = client.post(
        f"{_base(project_id)}/run",
        json={"auto_threshold": 0.4, "review_threshold": 0.9},
        headers=headers,
    )
    assert response.status_code == 422


def test_run_without_a_schedule_is_a_clear_error(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project_id = client.post(
        "/api/v1/projects",
        json={"code": f"NOSCHED-{uuid.uuid4().hex[:6]}", "name": "No schedule"},
        headers=headers,
    ).json()["id"]
    response = client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_SCHEDULE"


# --------------------------------------------------------------------- review
def _first_match(client: TestClient, project_id, headers, status: str | None = None):
    params = {"limit": 50}
    if status:
        params["status"] = status
    rows = client.get(f"{_base(project_id)}/matches", params=params, headers=headers).json()
    return rows["items"][0] if rows["items"] else None


def test_confirm_preserves_the_machine_verdict(client: TestClient, project) -> None:
    """auto_status is how the matcher's precision gets measured later."""
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers, MatchStatus.AUTO_MATCHED)
    assert match

    response = client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "confirm", "note": "checked against site diary"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == MatchStatus.MANUALLY_CONFIRMED
    assert body["auto_status"] == MatchStatus.AUTO_MATCHED
    assert body["reviewed_by_id"] is not None
    assert body["review_note"] == "checked against site diary"


def test_reject_clears_the_link(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers, MatchStatus.AUTO_MATCHED)
    response = client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "reject"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == MatchStatus.MANUALLY_REJECTED
    assert response.json()["activity_id"] is None


def test_reassign_moves_the_link(client: TestClient, project, db: Session) -> None:
    project_id, headers, schedule, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers, MatchStatus.AUTO_MATCHED)

    target = next(
        a for a in db.query(Activity).filter_by(schedule_id=schedule.id).all()
        if str(a.id) != match["activity_id"]
    )
    response = client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "reassign", "activity_id": str(target.id)},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["activity_id"] == str(target.id)
    assert response.json()["status"] == MatchStatus.MANUALLY_CONFIRMED


def test_reassign_requires_a_target(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers)
    response = client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "reassign"},
        headers=headers,
    )
    assert response.status_code == 422


def test_cannot_reassign_to_another_projects_activity(
    client: TestClient, project, make_user, auth_headers, db: Session
) -> None:
    """The tenancy boundary must hold even for an authorised reviewer."""
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers)

    other_manager = make_user(UserRole.PROJECT_MANAGER)
    other_headers = auth_headers(other_manager)
    other_id = uuid.UUID(
        client.post(
            "/api/v1/projects",
            json={"code": f"OTHER-{uuid.uuid4().hex[:6]}", "name": "Other"},
            headers=other_headers,
        ).json()["id"]
    )
    other_schedule, _ = _seed(db, other_id, other_manager.id)
    foreign = db.query(Activity).filter_by(schedule_id=other_schedule.id).first()

    response = client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "reassign", "activity_id": str(foreign.id)},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CROSS_PROJECT_ACTIVITY"


def test_review_history_records_every_decision(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    match = _first_match(client, project_id, headers, MatchStatus.AUTO_MATCHED)

    client.post(f"{_base(project_id)}/matches/{match['id']}/review",
                json={"decision": "confirm"}, headers=headers)
    client.post(f"{_base(project_id)}/matches/{match['id']}/review",
                json={"decision": "reject", "note": "wrong on second look"}, headers=headers)

    history = client.get(
        f"{_base(project_id)}/matches/{match['id']}/history", headers=headers
    ).json()
    assert len(history) == 2
    assert history[0]["details"]["decision"] == "confirm"
    assert history[1]["details"]["decision"] == "reject"
    assert history[1]["details"]["machine_status"] == MatchStatus.AUTO_MATCHED


def test_stats_reports_measured_precision(client: TestClient, project) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)

    before = client.get(f"{_base(project_id)}/stats", headers=headers).json()
    assert before["auto_precision"] is None, "no reviews yet, so no measured number"
    assert before["total"] > 0

    match = _first_match(client, project_id, headers, MatchStatus.AUTO_MATCHED)
    client.post(f"{_base(project_id)}/matches/{match['id']}/review",
                json={"decision": "confirm"}, headers=headers)

    after = client.get(f"{_base(project_id)}/stats", headers=headers).json()
    assert after["reviewed_count"] == 1
    assert after["auto_precision"] == 1.0
    assert after["manually_confirmed"] == 1


# ------------------------------------------------------------------ authz
def test_supervisor_can_read_but_not_run_or_review(
    client: TestClient, project, supervisor_user, auth_headers
) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": supervisor_user.email, "role": "SITE_SUPERVISOR"},
        headers=headers,
    )
    sup = auth_headers(supervisor_user)

    assert client.get(f"{_base(project_id)}/matches", headers=sup).status_code == 200
    assert client.get(f"{_base(project_id)}/stats", headers=sup).status_code == 200
    assert client.post(f"{_base(project_id)}/run", json={}, headers=sup).status_code == 403

    match = _first_match(client, project_id, headers)
    assert client.post(
        f"{_base(project_id)}/matches/{match['id']}/review",
        json={"decision": "confirm"}, headers=sup,
    ).status_code == 403


def test_non_member_sees_nothing(client: TestClient, project, make_user, auth_headers) -> None:
    project_id, headers, _, _ = project
    client.post(f"{_base(project_id)}/run", json={}, headers=headers)
    outsider = auth_headers(make_user(UserRole.PROJECT_MANAGER))
    assert client.get(f"{_base(project_id)}/matches", headers=outsider).status_code == 404
    assert client.get(f"{_base(project_id)}/stats", headers=outsider).status_code == 404
    assert client.post(f"{_base(project_id)}/run", json={}, headers=outsider).status_code == 404


def test_matching_requires_authentication(client: TestClient, project) -> None:
    project_id, _, _, _ = project
    assert client.get(f"{_base(project_id)}/matches").status_code == 401
