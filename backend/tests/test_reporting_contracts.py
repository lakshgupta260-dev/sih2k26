"""Phase 8 model-registration and schema-contract tests."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.constants import GeneratedReportFormat, NotificationChannel
from app.db.base import Base
from app.schemas.reporting import GeneratedReportCreate, NotificationCreate


def test_phase_8_models_are_registered_for_alembic() -> None:
    assert "generated_reports" in Base.metadata.tables
    assert "notifications" in Base.metadata.tables


def test_generated_report_request_has_isolated_parameters() -> None:
    first = GeneratedReportCreate(report_type="progress_summary", output_format=GeneratedReportFormat.PDF)
    second = GeneratedReportCreate(report_type="progress_summary", output_format=GeneratedReportFormat.XLSX)
    first.parameters["discipline"] = "CIVIL"
    assert second.parameters == {}


def test_in_app_notification_requires_a_user_recipient() -> None:
    with pytest.raises(ValidationError, match="recipient_user_id"):
        NotificationCreate(
            channel=NotificationChannel.IN_APP,
            notification_type="delay_risk",
            title="Risk updated",
            body="A delay risk needs review.",
        )

    notification = NotificationCreate(
        channel=NotificationChannel.IN_APP,
        recipient_user_id=uuid.uuid4(),
        notification_type="delay_risk",
        title="Risk updated",
        body="A delay risk needs review.",
    )
    assert notification.recipient_user_id is not None
