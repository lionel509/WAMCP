import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json
from app.services.whatsapp_messenger import WhatsAppMessenger


@pytest.fixture
def messenger_no_token():
    """Create a messenger instance with no token for testing."""
    with patch("app.services.whatsapp_messenger.settings") as mock_settings:
        mock_settings.whatsapp_access_token = None
        mock_settings.whatsapp_api_version = "v24.0"
        mock_settings.whatsapp_base_url = "https://graph.facebook.com"
        mock_settings.whatsapp_phone_number_id = "875171289009578"
        return WhatsAppMessenger()


@pytest.fixture
def messenger_with_token():
    """Create a messenger instance with token for testing."""
    with patch("app.services.whatsapp_messenger.settings") as mock_settings:
        mock_settings.whatsapp_access_token = "test-token"
        mock_settings.whatsapp_api_version = "v24.0"
        mock_settings.whatsapp_base_url = "https://graph.facebook.com"
        mock_settings.whatsapp_phone_number_id = "875171289009578"
        return WhatsAppMessenger()


@pytest.mark.asyncio
async def test_send_text_missing_token(messenger_no_token):
    """When token is missing, send_text should return error."""
    result = await messenger_no_token.send_text(
        to="15169007810",
        body="Test message"
    )
    assert "error" in result
    assert result["error_type"] == "missing_token"


@pytest.mark.asyncio
async def test_send_text_missing_phone_id():
    """When phone ID is missing, send_text should return error."""
    with patch("app.services.whatsapp_messenger.settings") as mock_settings:
        mock_settings.whatsapp_access_token = "test-token"
        mock_settings.whatsapp_api_version = "v24.0"
        mock_settings.whatsapp_base_url = "https://graph.facebook.com"
        mock_settings.whatsapp_phone_number_id = None
        
        messenger = WhatsAppMessenger()
        result = await messenger.send_text(
            to="15169007810",
            body="Test message"
        )
        assert "error" in result
        assert result["error_type"] == "missing_phone_id"


@pytest.mark.asyncio
async def test_send_text_placeholder_phone_id():
    """When phone ID is a placeholder like 'string', should return error."""
    with patch("app.services.whatsapp_messenger.settings") as mock_settings:
        mock_settings.whatsapp_access_token = "test-token"
        mock_settings.whatsapp_api_version = "v24.0"
        mock_settings.whatsapp_base_url = "https://graph.facebook.com"
        mock_settings.whatsapp_phone_number_id = "string"
        
        messenger = WhatsAppMessenger()
        result = await messenger.send_text(
            to="15169007810",
            body="Test message"
        )
        assert "error" in result
        assert result["error_type"] == "placeholder_config"
        assert "placeholder" in result["error"].lower()


@pytest.mark.asyncio
async def test_graph_error_parsing_with_error_payload(messenger_with_token):
    """When Meta returns a 400 error with JSON, should parse and log it."""
    graph_error_response = {
        "error": {
            "message": "Invalid phone number format",
            "type": "OAuthException",
            "code": 400,
            "fbtrace_id": "AbCdEfGhIjKlMnOpQrStUvWxYz"
        }
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = json.dumps(graph_error_response)
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        with patch("app.services.whatsapp_messenger.logger") as mock_logger:
            result = await messenger_with_token.send_text(
                to="invalid",
                body="Test"
            )
            
            # Verify error was parsed
            assert result["error"] == "graph_api_error"
            assert result["status_code"] == 400
            assert "Invalid phone number format" in result["details"].get("message", "")
            
            # Verify error was logged
            mock_logger.error.assert_called()
            log_call = mock_logger.error.call_args[0][0]
            assert "Invalid phone number format" in log_call
            assert "400" in log_call


@pytest.mark.asyncio
async def test_graph_error_with_invalid_json(messenger_with_token):
    """When Meta returns invalid JSON, should log raw response."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error - not JSON"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        with patch("app.services.whatsapp_messenger.logger") as mock_logger:
            result = await messenger_with_token.send_text(
                to="15169007810",
                body="Test"
            )
            
            # Verify error returned
            assert result["error"] == "graph_api_error"
            assert result["status_code"] == 500
            
            # Verify raw response logged
            mock_logger.error.assert_called()
            log_call = mock_logger.error.call_args[0][0]
            assert "Internal Server Error" in log_call


@pytest.mark.asyncio
async def test_graph_error_with_fbtrace_id(messenger_with_token):
    """FBTrace ID should be included in logs for debugging."""
    graph_error_response = {
        "error": {
            "message": "Access token validation failed",
            "code": 401,
            "fbtrace_id": "TestTraceId123"
        }
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = json.dumps(graph_error_response)
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        with patch("app.services.whatsapp_messenger.logger") as mock_logger:
            result = await messenger_with_token.send_text(
                to="15169007810",
                body="Test"
            )
            
            # Verify fbtrace_id is in the result
            assert result["details"].get("fbtrace_id") == "TestTraceId123"
            
            # Verify it's logged
            log_call = mock_logger.error.call_args[0][0]
            assert "TestTraceId123" in log_call


@pytest.mark.asyncio
async def test_send_text_http_exception(messenger_with_token):
    """HTTP exceptions should be caught and logged."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Connection timeout")
        )
        
        with patch("app.services.whatsapp_messenger.logger") as mock_logger:
            result = await messenger_with_token.send_text(
                to="15169007810",
                body="Test"
            )
            
            assert "error" in result
            assert result["error_type"] == "http_error"
            mock_logger.error.assert_called()
