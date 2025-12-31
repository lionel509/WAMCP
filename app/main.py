import logging
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.messages import router as messages_router
from app.config import settings
from app.db.session import get_db
from app.services.ingest_service import IngestService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

webhook_router = APIRouter()
ops_router = APIRouter(prefix="/admin")
core_router = APIRouter()


@core_router.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV}


@webhook_router.get("/webhooks/whatsapp")
async def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    """
    Handle Webhook Verification Challenge from Meta.
    Meta sends this GET request to verify the webhook endpoint.
    """
    from app.services.structured_logging import StructuredLogger

    if not settings.whatsapp_verify_token:
        logger.error("Webhook verification token not configured")
        StructuredLogger.log_webhook_verification(success=False, mode=mode)
        raise HTTPException(status_code=500, detail="Verification token not configured")

    success = mode == "subscribe" and token == settings.whatsapp_verify_token

    if success:
        logger.info(f"Webhook verification successful for mode={mode}")
        StructuredLogger.log_webhook_verification(success=True, mode=mode)
        return Response(content=challenge, media_type="text/plain")

    logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == settings.whatsapp_verify_token}")
    StructuredLogger.log_webhook_verification(success=False, mode=mode)
    raise HTTPException(status_code=403, detail="Verification failed")


@ops_router.get("/watchdog/status")
async def get_watchdog_status(api_key: str = Query(..., alias="api_key"), db: AsyncSession = Depends(get_db)):
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    from app.db.models import WatchdogRun
    from sqlalchemy import desc, select

    stmt = select(WatchdogRun).order_by(desc(WatchdogRun.ran_at)).limit(10)
    result = await db.execute(stmt)
    runs = result.scalars().all()

    return [{"id": r.id, "ran_at": r.ran_at, "status": r.status_json} for r in runs]


@webhook_router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive Webhook Events from Meta WhatsApp Cloud API.
    Handles incoming messages, statuses, and other events.
    """
    import uuid
    from app.services.structured_logging import StructuredLogger

    request_id = str(uuid.uuid4())

    try:
        raw_body = await request.body()
        headers = dict(request.headers)

        logger.info(f"Webhook received. request_id={request_id}, body_size={len(raw_body)}")

        ingest_service = IngestService(db)
        result = await ingest_service.ingest_webhook(raw_body, headers, request_id=request_id)

        return {"ok": True, "request_id": request_id, **result}

    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}", exc_info=True)
        StructuredLogger.log_webhook_error(
            request_id=request_id,
            error_message=str(e)[:100],  # Safe truncation
            exception_class=type(e).__name__,
        )
        return {"ok": False, "request_id": request_id, "error": str(e)[:100]}


async def _check_db_connectivity(url: str) -> bool:
    try:
        engine = create_async_engine(url, future=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        logger.warning("Database connectivity check failed", exc_info=True)
        return False


def create_app(plugin_mode: Optional[bool] = None) -> FastAPI:
    mode = settings.plugin_mode if plugin_mode is None else plugin_mode
    app = FastAPI(title="WAMCP API")
    app.include_router(health_router)
    app.include_router(core_router)

    if not mode:
        app.include_router(admin_router)
        app.include_router(messages_router)
        app.include_router(webhook_router)
        app.include_router(ops_router)
    else:
        logger.info("Plugin mode enabled: webhook and admin/message routes are disabled")

    @app.on_event("startup")
    async def startup_event():
        public_url_state = "set" if settings.public_base_url else "unset"
        audit_db_enabled = bool(settings.audit_database_url)

        db_connected = await _check_db_connectivity(settings.DATABASE_URL)
        audit_connected = False
        if audit_db_enabled:
            audit_connected = await _check_db_connectivity(settings.audit_database_url)  # type: ignore[arg-type]

        logger.info(
            "startup config: plugin_mode=%s db_connected=%s audit_db_enabled=%s audit_db_connected=%s public_base_url=%s",
            mode,
            db_connected,
            audit_db_enabled,
            audit_connected,
            public_url_state,
        )

        if mode and not db_connected:
            raise RuntimeError("Plugin mode requires read-only DB connectivity to the messaging database")

        if not mode and settings.debug_echo_mode:
            logger.warning("⚠️  DEBUG_ECHO_MODE=true - Messages will be echoed back (dev only)")

    return app


app = create_app()
