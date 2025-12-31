from fastapi import FastAPI, Request, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db.session import get_db
from app.services.ingest_service import IngestService
from app.api.admin import router as admin_router
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WAMCP API")
app.include_router(admin_router)

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
    """
    if not settings.whatsapp_verify_token:
        logger.error("Webhook verification token not configured")
        raise HTTPException(status_code=500, detail="Verification token not configured")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("Webhook verification successful")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed.")
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
    Receive Webhook Events.
    """
    # Read raw body for signature verification and hashing
    raw_body = await request.body()
    headers = dict(request.headers)
    
    ingest_service = IngestService(db)
    result = await ingest_service.ingest_webhook(raw_body, headers)
    
    return result
