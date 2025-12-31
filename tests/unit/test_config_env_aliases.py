import os
import pytest

from app.config import Settings


CANONICAL_AND_ALIASES = [
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_API_TOKEN",
    "WHATSAPP_API_KEY",
    "WHATSAPP_TOKEN",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
    "WHATSAPP_VERIFY",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_SECRET",
    "APP_SECRET",
    "VERIFY_WEBHOOK_SIGNATURE",
    "VERIFY_WEBHOOK",
    "VERIFY_SIGNATURE",
    "WHATSAPP_PHONE_NUMBER_ID",
    "PHONE_NUMBER_ID",
    "WHATSAPP_WABA_ID",
    "WHATSAPP_BUSINESS_ACCOUNT_ID",
    "WABA_ID",
    "DEBUG_ECHO_MODE",
    "DEBUG_ECHO_ALLOWLIST_E164",
    "DEBUG_ECHO_RATE_LIMIT_SECONDS",
    "DEBUG_ECHO_GROUP_FALLBACK",
    "WHATSAPP_API_VERSION",
    "WHATSAPP_BASE_URL",
]


def clear_env(monkeypatch):
    for key in CANONICAL_AND_ALIASES:
        monkeypatch.delenv(key, raising=False)


def test_canonical_values_preferred(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "canonical-token")
    monkeypatch.setenv("WHATSAPP_API_TOKEN", "legacy-token")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "false")

    settings = Settings(_env_file=None)

    assert settings.whatsapp_access_token == "canonical-token"
    assert settings.whatsapp_app_secret == "secret"


def test_legacy_values_resolved(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("WHATSAPP_API_TOKEN", "legacy-token")
    monkeypatch.setenv("PHONE_NUMBER_ID", "legacy-phone")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "false")

    settings = Settings(_env_file=None)

    assert settings.whatsapp_access_token == "legacy-token"
    assert settings.whatsapp_phone_number_id == "legacy-phone"


def test_missing_app_secret_raises_when_verification_enabled(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "true")

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_missing_access_token_raises_when_debug_true(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("DEBUG_ECHO_MODE", "true")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "false")

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_boolean_parsing_supports_common_values(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "0")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")

    settings_false = Settings(_env_file=None)
    assert settings_false.verify_webhook_signature is False

    clear_env(monkeypatch)
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "1")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")

    settings_true = Settings(_env_file=None)
    assert settings_true.verify_webhook_signature is True


def test_startup_allowed_when_signature_disabled(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "false")
    monkeypatch.setenv("DEBUG_ECHO_MODE", "false")

    settings = Settings(_env_file=None)
    assert settings.verify_webhook_signature is False


def test_startup_with_signature_enabled_and_secret(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("VERIFY_WEBHOOK_SIGNATURE", "true")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret")

    settings = Settings(_env_file=None)
    assert settings.verify_webhook_signature is True
    assert settings.whatsapp_app_secret == "secret"
