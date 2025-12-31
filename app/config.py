from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_ENV: str = "dev"
    API_PORT: int = 8000
    
    # Watchdog & Reliability
    WATCHDOG_ENABLED: bool = True
    WATCHDOG_INTERVAL_SECONDS: int = 60
    WATCHDOG_STUCK_MESSAGE_MINUTES: int = 5
    WATCHDOG_MAX_QUEUE_BACKLOG: int = 500
    WATCHDOG_MAX_PENDING_DOCS: int = 200
    WATCHDOG_MAX_FAILED_DOCS: int = 50
    WATCHDOG_NOTIFY_MODE: str = "log" # log | admin_whatsapp_debug
    WATCHDOG_ADMIN_NOTIFY_E164: Optional[str] = None
    WATCHDOG_REENQUEUE_STALLED_DOCS: bool = True
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/wamcp"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_DOCUMENTS: str = "documents"
    MINIO_SECURE: bool = False

    # WhatsApp
    WHATSAPP_VERIFY_TOKEN: str = "dev-verify-token"
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None
    VERIFY_WEBHOOK_SIGNATURE: bool = True

    # Debug / Safety
    DEBUG_ECHO_MODE: bool = False
    DEBUG_ECHO_ALLOWLIST_E164: str = "" # Comma separated
    DEBUG_ECHO_ALLOW_GROUP_IDS: str = "" # Comma separated
    DEBUG_ECHO_RATE_LIMIT_SECONDS: int = 60
    
    # Admin
    ADMIN_API_KEY: str = "dev-admin-key"

settings = Settings()
