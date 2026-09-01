"""Health, error-envelope and OpenAPI contract tests."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert "version" in body


def test_liveness_sets_request_id_header(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Request-ID")


def test_liveness_echoes_supplied_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_readiness_reports_database_state(client: TestClient) -> None:
    """Readiness must answer either way -- 200 when the DB is up, 503 when not."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["database"] in ("up", "down")
    assert body["checks_passed"] is (response.status_code == 200)


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert set(body["error"]) == {"code", "message", "details"}


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/health" in schema["paths"]
