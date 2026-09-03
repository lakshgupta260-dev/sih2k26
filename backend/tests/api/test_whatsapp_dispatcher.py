import pytest
from unittest.mock import patch, MagicMock
from app.notifications.whatsapp import WhatsAppDispatcher
from app.models.reporting import Notification
from app.core.config import settings

@patch("app.notifications.whatsapp.httpx.Client")
def test_whatsapp_dispatcher_dry_run(mock_client, monkeypatch):
    monkeypatch.setattr(settings, "META_ACCESS_TOKEN", None)
    monkeypatch.setattr(settings, "META_PHONE_NUMBER_ID", None)
    
    dispatcher = WhatsAppDispatcher()
    notification = Notification(
        recipient_address="1234567890",
        body="Test message"
    )
    
    result = dispatcher.dispatch(notification)
    assert result.success is True
    assert result.provider_message_id.startswith("wa_msg_")
    
    # Should not use httpx
    mock_client.assert_not_called()

@patch("app.notifications.whatsapp.httpx.Client")
def test_whatsapp_dispatcher_live(mock_client, monkeypatch):
    monkeypatch.setattr(settings, "META_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(settings, "META_PHONE_NUMBER_ID", "mock_id")
    
    # Mock httpx context manager
    mock_client_instance = MagicMock()
    mock_client.return_value.__enter__.return_value = mock_client_instance
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"messages": [{"id": "real_msg_id"}]}
    mock_client_instance.post.return_value = mock_response
    
    dispatcher = WhatsAppDispatcher()
    notification = Notification(
        recipient_address="1234567890",
        body="Test message live"
    )
    
    result = dispatcher.dispatch(notification)
    assert result.success is True
    assert result.provider_message_id == "real_msg_id"
    
    mock_client_instance.post.assert_called_once()
