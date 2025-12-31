import logging
from sqlalchemy import text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.config import settings
from app.db.models import RawEvent, Document, ExtractionStatus
from app.integrations.minio_client import minio_client
import redis

logger = logging.getLogger(__name__)

async def check_dependencies(db: AsyncSession, redis_client: redis.Redis) -> dict:
    status = {"postgres": False, "redis": False, "minio": False}
    
    # Postgres
    try:
        await db.execute(text("SELECT 1"))
        status["postgres"] = True
    except Exception as e:
        logger.error(f"Dependency Check Postgres Failed: {e}")
        
    # Redis
    try:
        if redis_client.ping():
            status["redis"] = True
    except Exception as e:
        logger.error(f"Dependency Check Redis Failed: {e}")
        
    # MinIO
    try:
        if minio_client.client.bucket_exists(minio_client.bucket):
            status["minio"] = True
        else:
            logger.error(f"MinIO Bucket {minio_client.bucket} missing")
    except Exception as e:
        logger.error(f"Dependency Check MinIO Failed: {e}")

    return status

async def check_ingestion_health(db: AsyncSession) -> list:
    alerts = []
    
    # 1. Recent Ingestion (Informational check mostly, unless critical)
    # Check if ANY raw event in last 15 min
    since = datetime.utcnow() - timedelta(minutes=15)
    stmt = select(func.count(RawEvent.id)).where(RawEvent.received_at > since)
    res = await db.execute(stmt)
    count = res.scalar() or 0
    
    # If 0, we might log info, but not necessarily alert if low volume.
    # But if we expect traffic, this detects silence.
    # We'll just log stats for now.
    
    # 2. Signature failures (High alert)
    stmt_sig = select(func.count(RawEvent.id)).where(RawEvent.received_at > since, RawEvent.signature_valid == False)
    res_sig = await db.execute(stmt_sig)
    sig_fails = res_sig.scalar() or 0
    
    if sig_fails > 5: # Threshold
        alerts.append({"type": "ingestion_signature_failures", "count": sig_fails, "window": "15m"})
        
    return alerts

async def check_document_health(db: AsyncSession) -> tuple[list, list]:
    alerts = []
    stalled_ids = []
    
    # 1. Pending too long
    threshold_mins = settings.WATCHDOG_STUCK_MESSAGE_MINUTES
    cutoff = datetime.utcnow() - timedelta(minutes=threshold_mins)
    
    stmt_pending = select(Document.id).where(
        Document.extraction_status == ExtractionStatus.PENDING,
        Document.created_at < cutoff
    ).limit(settings.WATCHDOG_MAX_PENDING_DOCS + 1)
    
    res = await db.execute(stmt_pending)
    pending_ids = res.scalars().all()
    
    if len(pending_ids) > 0:
        alerts.append({"type": "stalled_documents", "count": len(pending_ids), "threshold_min": threshold_mins})
        stalled_ids = [str(pid) for pid in pending_ids]
        
    # 2. Failed too many
    since_hour = datetime.utcnow() - timedelta(hours=1)
    stmt_failed = select(func.count(Document.id)).where(
        Document.extraction_status == ExtractionStatus.FAILED,
        Document.created_at > since_hour
    )
    res_failed = await db.execute(stmt_failed)
    failed_count = res_failed.scalar() or 0
    
    if failed_count > settings.WATCHDOG_MAX_FAILED_DOCS:
        alerts.append({"type": "high_failure_rate_docs", "count": failed_count, "window": "1h"})
        
    return alerts, stalled_ids

async def check_queue_health(redis_client: redis.Redis) -> list:
    alerts = []
    # Celery queue length
    # Default queue key: 'celery'
    try:
        q_len = redis_client.llen("celery")
        if q_len > settings.WATCHDOG_MAX_QUEUE_BACKLOG:
             alerts.append({"type": "queue_backlog", "count": q_len, "limit": settings.WATCHDOG_MAX_QUEUE_BACKLOG})
    except Exception as e:
        logger.error(f"Queue Check Failed: {e}")
        
    return alerts
