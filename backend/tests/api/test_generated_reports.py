"""API integration tests for generated reports endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
