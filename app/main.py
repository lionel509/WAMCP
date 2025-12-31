from fastapi import FastAPI, Request, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db.session import get_db
from app.services.ingest_service import IngestService
from app.api.admin import router as admin_router
from app.api.messages import router as messages_router
from app.api.health import router as health_router
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WAMCP API")
app.include_router(health_router)
app.include_router(admin_router)
app.include_router(messages_router)

# Log startup configuration
@app.on_event("startup")
async def startup_event():
    """Log configuration on startup."""
    logger.info(f"WAMCP API starting in {settings.APP_ENV} environment")
    
    if settings.public_base_url:
        logger.info(f"Public Base URL: {settings.public_base_url}")
        logger.info(f"Webhook Callback URL for Meta: {settings.get_webhook_callback_url()}")
    else:
        logger.info("PUBLIC_BASE_URL not set - using relative URLs (works for local dev)")
        logger.info("For production/tunnel: set PUBLIC_BASE_URL environment variable")
    
    if settings.debug_echo_mode:
        logger.warning("⚠️  DEBUG_ECHO_MODE=true - Messages will be echoed back (dev only)")
    
    logger.info("✓ WAMCP API ready to receive webhooks")

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV}

@app.get("/webhooks/whatsapp")
async def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge")
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

@app.get("/admin/watchdog/status")
async def get_watchdog_status(
    api_key: str = Query(..., alias="api_key"),
    db: AsyncSession = Depends(get_db)
):
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
        
    from app.db.models import WatchdogRun
    from sqlalchemy import desc, select
    
    stmt = select(WatchdogRun).order_by(desc(WatchdogRun.ran_at)).limit(10)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    return [
        {"id": r.id, "ran_at": r.ran_at, "status": r.status_json}
        for r in runs
    ]

@app.post("/webhooks/whatsapp")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive Webhook Events from Meta WhatsApp Cloud API.
    Handles incoming messages, statuses, and other events.
    """
    import uuid
    from app.services.structured_logging import StructuredLogger
    
    request_id = str(uuid.uuid4())
    
    try:
        # Read raw body for signature verification
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
            exception_class=type(e).__name__
        )
        # Always return 200 to avoid Meta retries, but log the error
        return {"ok": False, "request_id": request_id, "error": str(e)[:100]}
