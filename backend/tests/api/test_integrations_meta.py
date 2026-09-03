import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.core.config import settings
from app.models.document import UploadedFile, ProcessingJob

def test_meta_webhook_verification_success(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "META_VERIFY_TOKEN", "my_secret_token")
    
    response = client.get(
        "/api/v1/integrations/meta/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "my_secret_token"
        }
    )
    
    assert response.status_code == 200
    assert response.text == "1158201444"


def test_meta_webhook_verification_failure(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "META_VERIFY_TOKEN", "my_secret_token")
    
    response = client.get(
        "/api/v1/integrations/meta/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "wrong_token"
        }
    )
    
    assert response.status_code == 403


@patch("app.tasks.document_tasks.process_uploaded_file.delay")
def test_meta_webhook_receive_message(mock_delay, client: TestClient, db: Session, monkeypatch, manager_user, test_project):
    monkeypatch.setattr(settings, "META_APP_SECRET", "test_secret")
    
    # We assign a phone number to our manager_user
    manager_user.phone = "1234567890"
    db.commit()
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "16505551111",
                                "phone_number_id": "123456123"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Manager"
                                    },
                                    "wa_id": "1234567890"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "1234567890",
                                    "id": "wamid.HBgLMTY1MD...",
                                    "timestamp": "1602320431",
                                    "text": {
                                        "body": "Progress report: Completed 50 units on A100."
                                    },
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    
    payload_bytes = json.dumps(payload).encode()
    signature = hmac.new(
        b"test_secret", payload_bytes, hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json"
    }
    
    response = client.post(
        "/api/v1/integrations/meta/webhook",
        content=payload_bytes,
        headers=headers
    )
    
    assert response.status_code == 200
    
    # Verify UploadedFile and Job created
    uploaded_file = db.query(UploadedFile).filter_by(uploaded_by_id=manager_user.id).first()
    assert uploaded_file is not None
    assert str(uploaded_file.project_id) == test_project[0]
    
    job = db.query(ProcessingJob).filter_by(uploaded_file_id=uploaded_file.id).first()
    assert job is not None
    
    mock_delay.assert_called_once_with(str(job.id))
