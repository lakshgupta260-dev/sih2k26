import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.core.config import settings
from app.models.document import UploadedFile, ProcessingJob

def test_vapi_webhook_verification_failure(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "VAPI_SECRET", "super_secret")
    
    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        headers={"x-vapi-secret": "wrong_secret"},
        json={"message": {"type": "end-of-call-report"}}
    )
    
    assert response.status_code == 403

def test_vapi_webhook_verification_success(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "VAPI_SECRET", "super_secret")
    
    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        headers={"x-vapi-secret": "super_secret"},
        json={"message": {"type": "assistant-request"}}
    )
    
    assert response.status_code == 200

@patch("app.tasks.document_tasks.process_uploaded_file.delay")
def test_vapi_end_of_call_report(mock_delay, client: TestClient, db: Session, monkeypatch, manager_user, test_project):
    monkeypatch.setattr(settings, "VAPI_SECRET", "test-secret")
    
    manager_user.phone = "1234567890"
    manager_user.phone_normalised = "1234567890"
    db.commit()
    
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "customer": {
                    "number": "+1234567890"
                }
            },
            "transcript": "Progress update: A100 is done."
        }
    }
    
    response = client.post("/api/v1/integrations/vapi/webhook", json=payload, headers={"x-vapi-secret": "test-secret"})
    
    assert response.status_code == 200
    
    uploaded_file = db.query(UploadedFile).filter_by(uploaded_by_id=manager_user.id).first()
    assert uploaded_file is not None
    assert str(uploaded_file.project_id) == test_project[0]
    
    job = db.query(ProcessingJob).filter_by(uploaded_file_id=uploaded_file.id).first()
    assert job is not None
    
    mock_delay.assert_called_once_with(str(job.id))

def test_vapi_tool_call(client: TestClient, db: Session, monkeypatch, manager_user, test_project):
    monkeypatch.setattr(settings, "VAPI_SECRET", "test-secret")
    
    manager_user.phone = "1234567890"
    manager_user.phone_normalised = "1234567890"
    db.commit()
    
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "customer": {
                    "number": "+1234567890"
                }
            },
            "toolCalls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "get_project_progress",
                        "arguments": {}
                    }
                }
            ]
        }
    }
    
    response = client.post("/api/v1/integrations/vapi/webhook", json=payload, headers={"x-vapi-secret": "test-secret"})
    assert response.status_code == 200
    
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["toolCallId"] == "call_123"
    assert "Project:" in data["results"][0]["result"]
