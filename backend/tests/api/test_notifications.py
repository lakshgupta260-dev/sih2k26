"""API integration tests for notifications endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import NotificationChannel, UserRole
from app.schemas.reporting import NotificationCreate
from app.services.notification import NotificationService


def test_notifications_api_endpoints_flow(client: TestClient, db: Session, supervisor_user, auth_headers) -> None:
    headers = auth_headers(supervisor_user)
    service = NotificationService(db)

    # Seed 2 notifications for the supervisor user
    n1 = service.send_notification(
        NotificationCreate(
            channel=NotificationChannel.IN_APP,
            recipient_user_id=supervisor_user.id,
            notification_type="delay_alert",
            title="Warning 1",
            body="Delay detected in activity A1",
        )
    )
    n2 = service.send_notification(
        NotificationCreate(
            channel=NotificationChannel.IN_APP,
            recipient_user_id=supervisor_user.id,
            notification_type="delay_alert",
            title="Warning 2",
            body="Delay detected in activity A2",
        )
    )

    # 1. Unread count endpoint
    res_cnt = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_cnt.status_code == 200
    assert res_cnt.json()["unread_count"] == 2

    # 2. List notifications endpoint
    res_list = client.get("/api/v1/notifications", headers=headers)
    assert res_list.status_code == 200
    items = res_list.json()["items"]
    assert len(items) == 2

    # 3. Mark single notification as read
    res_read = client.patch(f"/api/v1/notifications/{n1.id}/read", headers=headers)
    assert res_read.status_code == 200
    assert res_read.json()["read_at"] is not None

    res_cnt2 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_cnt2.json()["unread_count"] == 1

    # 4. Mark all as read
    res_all = client.post("/api/v1/notifications/read-all", headers=headers)
    assert res_all.status_code == 200
    assert res_all.json()["updated_count"] == 1

    res_cnt3 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_cnt3.json()["unread_count"] == 0


def test_send_project_notification_endpoint(client: TestClient, test_project, supervisor_user) -> None:
    pid, headers = test_project

    res = client.post(
        f"/api/v1/projects/{pid}/notifications",
        json={
            "channel": "IN_APP",
            "recipient_user_id": str(supervisor_user.id),
            "notification_type": "schedule_update",
            "title": "New Baseline",
            "body": "Schedule baseline v2 published.",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["title"] == "New Baseline"
    assert data["recipient_user_id"] == str(supervisor_user.id)
