import pytest
from app.config import Settings, _is_placeholder


class TestIsPlaceholder:
    """Test the _is_placeholder helper function."""
    
    def test_none_value(self):
        """None should be considered a placeholder."""
        assert _is_placeholder(None) is False  # None is falsy, so returns False
    
    def test_empty_string(self):
        """Empty string should be considered a placeholder."""
        assert _is_placeholder("") is False  # Empty string is falsy
        assert _is_placeholder("   ") is False  # Whitespace only
    
    def test_literal_string(self):
        """The literal 'string' should be recognized as placeholder."""
        assert _is_placeholder("string") is True
        assert _is_placeholder("String") is True
        assert _is_placeholder("STRING") is True
    
    def test_replace_me_variants(self):
        """Various 'replace_me' formats should be recognized."""
        assert _is_placeholder("replace_me") is True
        assert _is_placeholder("replaceme") is True
        assert _is_placeholder("Replace_Me") is True
    
    def test_changeme(self):
        """'changeme' should be recognized."""
        assert _is_placeholder("changeme") is True
        assert _is_placeholder("CHANGEME") is True
    
    def test_todo(self):
        """'todo' should be recognized."""
        assert _is_placeholder("todo") is True
        assert _is_placeholder("TODO") is True
    
    def test_your_prefix(self):
        """Values starting with 'YOUR_' should be recognized."""
        assert _is_placeholder("YOUR_ACCESS_TOKEN") is True
        assert _is_placeholder("your_phone_id") is True
    
    def test_placeholder_suffix(self):
        """Values ending with '_PLACEHOLDER' should be recognized."""
        assert _is_placeholder("value_placeholder") is True
        assert _is_placeholder("TOKEN_PLACEHOLDER") is True
    
    def test_valid_values(self):
        """Valid non-placeholder values should return False."""
        assert _is_placeholder("875171289009578") is False
        assert _is_placeholder("abc123token") is False
        assert _is_placeholder("my_config_value") is False


class TestConfigValidation:
    """Test configuration validation on startup."""
    
    def test_phone_number_id_placeholder_raises_error(self):
        """When phone number ID is 'string', should raise ValueError on init."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                WHATSAPP_PHONE_NUMBER_ID="string",
                WHATSAPP_ACCESS_TOKEN="valid-token"
            )
        assert "placeholder" in str(exc_info.value).lower()
        assert "phone" in str(exc_info.value).lower()
    
    def test_phone_number_id_replace_me_raises_error(self):
        """When phone number ID is 'replace_me', should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                WHATSAPP_PHONE_NUMBER_ID="replace_me",
                WHATSAPP_ACCESS_TOKEN="valid-token"
            )
        assert "placeholder" in str(exc_info.value).lower()
    
    def test_debug_echo_mode_requires_access_token(self):
        """DEBUG_ECHO_MODE=true requires valid WHATSAPP_ACCESS_TOKEN."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                DEBUG_ECHO_MODE=True,
                WHATSAPP_PHONE_NUMBER_ID="875171289009578",
                WHATSAPP_ACCESS_TOKEN=None
            )
        assert "debug_echo_mode" in str(exc_info.value).lower()
        assert "access_token" in str(exc_info.value).lower()
    
    def test_debug_echo_mode_rejects_placeholder_token(self):
        """DEBUG_ECHO_MODE=true rejects placeholder tokens."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                DEBUG_ECHO_MODE=True,
                WHATSAPP_PHONE_NUMBER_ID="875171289009578",
                WHATSAPP_ACCESS_TOKEN="replace_me"
            )
        assert "debug_echo_mode" in str(exc_info.value).lower()
        assert "placeholder" in str(exc_info.value).lower()
    
    def test_debug_echo_mode_valid_config(self):
        """DEBUG_ECHO_MODE=true with valid config should succeed."""
        settings = Settings(
            DEBUG_ECHO_MODE=True,
            WHATSAPP_PHONE_NUMBER_ID="875171289009578",
            WHATSAPP_ACCESS_TOKEN="valid-token-from-meta"
        )
        assert settings.DEBUG_ECHO_MODE is True
        assert settings.whatsapp_phone_number_id == "875171289009578"
    
    def test_webhook_signature_requires_app_secret(self):
        """VERIFY_WEBHOOK_SIGNATURE=true requires WHATSAPP_APP_SECRET."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                VERIFY_WEBHOOK_SIGNATURE_PRIMARY=True,
                WHATSAPP_APP_SECRET=None,
            )
        assert "verify_webhook" in str(exc_info.value).lower()
        assert "app_secret" in str(exc_info.value).lower()
    
    def test_receiving_only_does_not_require_send_credentials(self):
        """When only receiving webhooks, send credentials are optional."""
        settings = Settings(
            DEBUG_ECHO_MODE=False,
            WHATSAPP_PHONE_NUMBER_ID=None,
            WHATSAPP_ACCESS_TOKEN=None
        )
        # Should not raise, since neither debug echo nor sending is enabled
        assert settings.DEBUG_ECHO_MODE is False
    
    def test_valid_phone_number_id_formats(self):
        """Valid phone number IDs should be accepted."""
        for valid_id in ["875171289009578", "123456789", "999999999999999"]:
            settings = Settings(WHATSAPP_PHONE_NUMBER_ID=valid_id)
            assert settings.whatsapp_phone_number_id == valid_id
