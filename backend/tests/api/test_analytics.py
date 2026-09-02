import pytest
from fastapi.testclient import TestClient
from datetime import date
from fastapi import status
import uuid

def test_analytics_summary(client: TestClient, auth_headers, manager_user):
    headers = auth_headers(manager_user)
    fake_project = str(uuid.uuid4())
    fake_schedule = str(uuid.uuid4())
    
    # Needs valid UUID format, but project might not exist.
    # Since auth passes, it will hit DB and likely return empty or 404 depending on how strict validation is.
    res = client.get(
        f"/api/v1/projects/{fake_project}/schedules/{fake_schedule}/analytics/summary",
        headers=headers
    )
    # Just checking it doesn't 500
    assert res.status_code in [200, 404]

def test_analytics_s_curve(client: TestClient, auth_headers, manager_user):
    headers = auth_headers(manager_user)
    fake_project = str(uuid.uuid4())
    fake_schedule = str(uuid.uuid4())
    
    res = client.get(
        f"/api/v1/projects/{fake_project}/schedules/{fake_schedule}/analytics/s-curve",
        headers=headers
    )
    assert res.status_code in [200, 404]
