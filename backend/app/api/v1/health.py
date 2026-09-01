"""Liveness and readiness endpoints.

``/health`` answers "is the process up". ``/health/ready`` additionally proves
the database is reachable, which is what an orchestrator should gate traffic on.
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.db.session import check_database_connection
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])

API_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        version=API_VERSION,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (verifies database connectivity)",
)
def readiness(response: Response) -> ReadinessResponse:
    db_ok = check_database_connection()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if db_ok else "degraded",
        database="up" if db_ok else "down",
        checks_passed=db_ok,
    )
