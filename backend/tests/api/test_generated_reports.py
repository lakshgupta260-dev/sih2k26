"""API integration tests for generated reports endpoints."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import JobStatus, PredictionMethod, RiskLevel
from app.models.prediction import DelayPrediction
from app.models.schedule import Activity, Schedule


def test_generated_report_create_list_and_download_flow(client: TestClient, test_project) -> None:
    pid, headers = test_project

    # 1. Request report generation
    res = client.post(
        f"/api/v1/projects/{pid}/generated-reports",
        json={
            "report_type": "progress_summary",
            "output_format": "PDF",
            "parameters": {"discipline": "CIVIL"},
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["report_type"] == "progress_summary"
    assert data["output_format"] == "PDF"
    report_id = data["id"]

    # 2. List generated reports
    list_res = client.get(
        f"/api/v1/projects/{pid}/generated-reports",
        headers=headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(x["id"] == report_id for x in list_data["items"])

    # 3. Get single report details
    get_res = client.get(
        f"/api/v1/projects/{pid}/generated-reports/{report_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report_id

    # 4. Download report file
    dl_res = client.get(
        f"/api/v1/projects/{pid}/generated-reports/{report_id}/download",
        headers=headers,
    )
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/pdf"
    assert dl_res.content.startswith(b"%PDF-")


def test_excel_report_generation_endpoint(client: TestClient, test_project) -> None:
    pid, headers = test_project

    res = client.post(
        f"/api/v1/projects/{pid}/generated-reports",
        json={
            "report_type": "executive_overview",
            "output_format": "XLSX",
            "parameters": {},
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    report_id = res.json()["id"]

    dl_res = client.get(
        f"/api/v1/projects/{pid}/generated-reports/{report_id}/download",
        headers=headers,
    )
    assert dl_res.status_code == 200
    assert "spreadsheetml" in dl_res.headers["content-type"]


def test_delay_risk_report_reflects_real_predictions_not_fabricated_defaults(
    client: TestClient, db: Session, test_project
) -> None:
    """The risk table must come from delay_predictions, not made-up defaults.

    Activity has no risk_band/risk_score/forecast_delay_days columns at all --
    an earlier version of this service read those via getattr(a, name,
    default) and silently got the default every time, so every report showed
    zero risk activities no matter what Phase 7's predictor actually forecast.
    This seeds one real HIGH-risk prediction and asserts it survives into the
    generated snapshot.
    """
    pid, headers = test_project

    schedule = Schedule(project_id=pid, name="Baseline", uploaded_by_id=None, status=JobStatus.COMPLETED)
    db.add(schedule)
    db.flush()

    activity = Activity(
        schedule_id=schedule.id,
        activity_code="A1",
        name="Pile foundation",
        wbs_path="1.A1",
        level=1,
    )
    db.add(activity)
    db.flush()

    prediction = DelayPrediction(
        project_id=pid,
        schedule_id=schedule.id,
        activity_id=activity.id,
        method=PredictionMethod.RULE_BASED_RATE,
        probability=0.91,
        predicted_late=True,
        risk_level=RiskLevel.HIGH,
        forecast_slip_days=14,
        as_of=date(2026, 6, 1),
    )
    db.add(prediction)
    db.commit()

    res = client.post(
        f"/api/v1/projects/{pid}/generated-reports",
        json={"report_type": "delay_risk", "output_format": "XLSX", "parameters": {}},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    snapshot = res.json()["snapshot"]

    assert snapshot["summary"]["high_risk_count"] == 1
    risk_rows = snapshot["risks"]
    assert len(risk_rows) == 1
    assert risk_rows[0]["code"] == "A1"
    assert risk_rows[0]["risk_band"] == "HIGH"
    assert risk_rows[0]["forecast_delay_days"] == 14
    assert risk_rows[0]["risk_score"] == pytest.approx(0.91)
