from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


def _first_non_empty(*values, default=None):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return default


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_placeholder(value: Optional[str]) -> bool:
    """
    Check if a value is a placeholder or placeholder-like.
    
    Returns True if value is:
    - None, empty string, or whitespace
    - "string" (literal)
    - "replace_me", "replaceme"
    - "changeme"
    - "todo" (case-insensitive)
    - Starts with "YOUR_" or ends with "_PLACEHOLDER"
    """
    if not value or not isinstance(value, str):
        return False
    
    normalized = value.strip().lower()
    
    placeholders = {
        "string",
        "replace_me",
        "replaceme",
        "changeme",
        "todo",
    }
    
    if normalized in placeholders:
        return True
    
    if normalized.startswith("your_") or normalized.endswith("_placeholder"):
        return True
    
    return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_ENV: str = "dev"
    API_PORT: int = 8000
    WAMCP_PLUGIN_MODE: bool = False

    # Watchdog & Reliability
    WATCHDOG_ENABLED: bool = True
    WATCHDOG_INTERVAL_SECONDS: int = 60
    WATCHDOG_STUCK_MESSAGE_MINUTES: int = 5
    WATCHDOG_MAX_QUEUE_BACKLOG: int = 500
    WATCHDOG_MAX_PENDING_DOCS: int = 200
    WATCHDOG_MAX_FAILED_DOCS: int = 50
    WATCHDOG_NOTIFY_MODE: str = "log"  # log | admin_whatsapp_debug
    WATCHDOG_ADMIN_NOTIFY_E164: Optional[str] = None
    WATCHDOG_REENQUEUE_STALLED_DOCS: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/wamcp"
    AUDIT_DATABASE_URL: Optional[str] = None

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: Optional[str] = Field(default=None, alias="MINIO_BUCKET")
    MINIO_BUCKET_DOCUMENTS: Optional[str] = Field(default=None, alias="MINIO_BUCKET_DOCUMENTS")
    MINIO_SECURE: bool = False

    # WhatsApp canonical + aliases
    WHATSAPP_VERIFY_TOKEN_PRIMARY: Optional[str] = Field(default=None, alias="WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_VERIFY_TOKEN_ALIAS_WEBHOOK: Optional[str] = Field(default=None, alias="WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    WHATSAPP_VERIFY_TOKEN_ALIAS_SHORT: Optional[str] = Field(default=None, alias="WHATSAPP_VERIFY")

    WHATSAPP_ACCESS_TOKEN_PRIMARY: Optional[str] = Field(default=None, alias="WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_ACCESS_TOKEN_ALIAS_API_TOKEN: Optional[str] = Field(default=None, alias="WHATSAPP_API_TOKEN")
    WHATSAPP_ACCESS_TOKEN_ALIAS_API_KEY: Optional[str] = Field(default=None, alias="WHATSAPP_API_KEY")
    WHATSAPP_ACCESS_TOKEN_ALIAS_TOKEN: Optional[str] = Field(default=None, alias="WHATSAPP_TOKEN")

    WHATSAPP_APP_SECRET_PRIMARY: Optional[str] = Field(default=None, alias="WHATSAPP_APP_SECRET")
    WHATSAPP_APP_SECRET_ALIAS_WA: Optional[str] = Field(default=None, alias="WHATSAPP_SECRET")
    WHATSAPP_APP_SECRET_ALIAS_APP: Optional[str] = Field(default=None, alias="APP_SECRET")

    WHATSAPP_PHONE_NUMBER_ID_PRIMARY: Optional[str] = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_PHONE_NUMBER_ID_ALIAS_SHORT: Optional[str] = Field(default=None, alias="PHONE_NUMBER_ID")

    WHATSAPP_WABA_ID_PRIMARY: Optional[str] = Field(default=None, alias="WHATSAPP_WABA_ID")
    WHATSAPP_WABA_ID_ALIAS_BUSINESS: Optional[str] = Field(default=None, alias="WHATSAPP_BUSINESS_ACCOUNT_ID")
    WHATSAPP_WABA_ID_ALIAS_WABA: Optional[str] = Field(default=None, alias="WABA_ID")

    WHATSAPP_API_VERSION: str = "v24.0"
    WHATSAPP_BASE_URL: str = "https://graph.facebook.com"

    VERIFY_WEBHOOK_SIGNATURE_PRIMARY: Optional[bool] = Field(default=None, alias="VERIFY_WEBHOOK_SIGNATURE")
    VERIFY_WEBHOOK_SIGNATURE_ALIAS_VERIFY_WEBHOOK: Optional[bool] = Field(default=None, alias="VERIFY_WEBHOOK")
    VERIFY_WEBHOOK_SIGNATURE_ALIAS_VERIFY_SIGNATURE: Optional[bool] = Field(default=None, alias="VERIFY_SIGNATURE")

    # Debug / Safety
    DEBUG_ECHO_MODE: bool = False
    DEBUG_ECHO_ALLOWLIST_E164_RAW: str = Field(default="", alias="DEBUG_ECHO_ALLOWLIST_E164")
    DEBUG_ECHO_ALLOW_GROUP_IDS: str = Field(default="", alias="DEBUG_ECHO_ALLOW_GROUP_IDS")
    DEBUG_ECHO_RATE_LIMIT_SECONDS: int = 60
    DEBUG_ECHO_GROUP_FALLBACK: bool = False
    MAX_DOCUMENT_BYTES: int = 10 * 1024 * 1024  # 10MB default limit for document processing

    # Admin
    ADMIN_API_KEY: str = "dev-admin-key"

    # Public URL (for external links, webhooks, etc.)
    # Leave empty to use the request URL (works for local dev)
    PUBLIC_BASE_URL: Optional[str] = Field(default=None, alias="PUBLIC_BASE_URL")

    @property
    def whatsapp_verify_token(self) -> Optional[str]:
        return _first_non_empty(
            self.WHATSAPP_VERIFY_TOKEN_PRIMARY,
            self.WHATSAPP_VERIFY_TOKEN_ALIAS_WEBHOOK,
            self.WHATSAPP_VERIFY_TOKEN_ALIAS_SHORT,
        )

    @property
    def whatsapp_access_token(self) -> Optional[str]:
        return _first_non_empty(
            self.WHATSAPP_ACCESS_TOKEN_PRIMARY,
            self.WHATSAPP_ACCESS_TOKEN_ALIAS_API_TOKEN,
            self.WHATSAPP_ACCESS_TOKEN_ALIAS_API_KEY,
            self.WHATSAPP_ACCESS_TOKEN_ALIAS_TOKEN,
        )

    @property
    def whatsapp_app_secret(self) -> Optional[str]:
        return _first_non_empty(
            self.WHATSAPP_APP_SECRET_PRIMARY,
            self.WHATSAPP_APP_SECRET_ALIAS_WA,
            self.WHATSAPP_APP_SECRET_ALIAS_APP,
        )

    @property
    def whatsapp_phone_number_id(self) -> Optional[str]:
        return _first_non_empty(
            self.WHATSAPP_PHONE_NUMBER_ID_PRIMARY,
            self.WHATSAPP_PHONE_NUMBER_ID_ALIAS_SHORT,
        )

    @property
    def whatsapp_waba_id(self) -> Optional[str]:
        return _first_non_empty(
            self.WHATSAPP_WABA_ID_PRIMARY,
            self.WHATSAPP_WABA_ID_ALIAS_BUSINESS,
            self.WHATSAPP_WABA_ID_ALIAS_WABA,
        )

    @property
    def whatsapp_api_version(self) -> str:
        return self.WHATSAPP_API_VERSION

    @property
    def whatsapp_base_url(self) -> str:
        return self.WHATSAPP_BASE_URL

    @property
    def verify_webhook_signature(self) -> bool:
        return bool(
            _first_non_empty(
                self.VERIFY_WEBHOOK_SIGNATURE_PRIMARY,
                self.VERIFY_WEBHOOK_SIGNATURE_ALIAS_VERIFY_WEBHOOK,
                self.VERIFY_WEBHOOK_SIGNATURE_ALIAS_VERIFY_SIGNATURE,
                default=True,
            )
        )

    @property
    def debug_echo_allowlist_e164(self) -> List[str]:
        return _split_csv(self.DEBUG_ECHO_ALLOWLIST_E164_RAW)

    @property
    def debug_echo_allow_group_ids(self) -> List[str]:
        return _split_csv(self.DEBUG_ECHO_ALLOW_GROUP_IDS)

    @property
    def minio_bucket(self) -> str:
        return _first_non_empty(self.MINIO_BUCKET, self.MINIO_BUCKET_DOCUMENTS, default="documents")

    @property
    def debug_echo_mode(self) -> bool:
        return self.DEBUG_ECHO_MODE

    @property
    def debug_echo_rate_limit_seconds(self) -> int:
        return self.DEBUG_ECHO_RATE_LIMIT_SECONDS

    @property
    def debug_echo_group_fallback(self) -> bool:
        return self.DEBUG_ECHO_GROUP_FALLBACK

    @property
    def admin_api_key(self) -> str:
        return self.ADMIN_API_KEY

    @property
    def public_base_url(self) -> Optional[str]:
        """Get the public base URL, sanitized (no trailing slash)."""
        if not self.PUBLIC_BASE_URL:
            return None
        return self.PUBLIC_BASE_URL.rstrip("/")

    @property
    def plugin_mode(self) -> bool:
        return bool(self.WAMCP_PLUGIN_MODE)

    @property
    def audit_database_url(self) -> Optional[str]:
        return self.AUDIT_DATABASE_URL

    def get_webhook_callback_url(self) -> str:
        """Get the full webhook callback URL for Meta."""
        if self.public_base_url:
            return f"{self.public_base_url}/webhooks/whatsapp"
        return "/webhooks/whatsapp"  # Relative URL when no public URL set

    @model_validator(mode="after")
    def _validate_required_settings(self):
        if not self.plugin_mode:
            if self.verify_webhook_signature and not self.whatsapp_app_secret:
                raise ValueError(
                    "VERIFY_WEBHOOK_SIGNATURE=true requires WHATSAPP_APP_SECRET (or aliases WHATSAPP_SECRET / APP_SECRET)."
                )

            # Validate that phone number ID is not a placeholder
            if _is_placeholder(self.whatsapp_phone_number_id):
                import sys

                debug_msg = (
                    f"DEBUG: WHATSAPP_PHONE_NUMBER_ID_PRIMARY={self.WHATSAPP_PHONE_NUMBER_ID_PRIMARY} | "
                    f"WHATSAPP_PHONE_NUMBER_ID_ALIAS_SHORT={self.WHATSAPP_PHONE_NUMBER_ID_ALIAS_SHORT} | "
                    f"Resolved to: {self.whatsapp_phone_number_id}"
                )
                print(debug_msg, file=sys.stderr)
                raise ValueError(
                    f"WHATSAPP_PHONE_NUMBER_ID is set to a placeholder value '{self.whatsapp_phone_number_id}'. "
                    "Please configure it with your actual phone number ID from Meta (e.g., 875171289009578). "
                    "Get this from Meta App Dashboard > WhatsApp > Phone Numbers."
                )

            if self.DEBUG_ECHO_MODE:
                if not self.whatsapp_access_token or _is_placeholder(self.whatsapp_access_token):
                    raise ValueError(
                        "DEBUG_ECHO_MODE=true requires a valid WHATSAPP_ACCESS_TOKEN (not a placeholder like 'replace_me'). "
                        "Get this from Meta App Dashboard > WhatsApp > API Setup."
                    )
                if not self.whatsapp_phone_number_id:
                    raise ValueError(
                        "DEBUG_ECHO_MODE=true requires WHATSAPP_PHONE_NUMBER_ID (or alias PHONE_NUMBER_ID)."
                    )

        return self


settings = Settings()
