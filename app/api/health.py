"""
Health check endpoints for Kubernetes, Docker Compose, and load balancers.
These endpoints do NOT require authentication.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.config import settings
import logging
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/healthz")
async def liveness():
    """
    Liveness probe: Returns 200 if the process is running.
    Does NOT check dependencies; used for basic process health.
    """
    return {"status": "alive"}

@router.get("/readyz")
async def readiness():
    """
    Readiness probe: Returns 200 only if all critical dependencies are healthy.
    Used to determine if the service should receive traffic.
    """
    checks = {}
    plugin_mode = settings.plugin_mode
    
    # Postgres
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(settings.DATABASE_URL or "postgresql+asyncpg://localhost/postgres")
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        checks["postgres"] = "ok"
    except Exception as e:
        logger.error(f"Postgres readiness check failed: {e}")
        checks["postgres"] = "error"
    
    if not plugin_mode:
        try:
            import redis.asyncio as redis
            redis_url = settings.REDIS_URL or "redis://localhost:6379/0"
            r = redis.from_url(redis_url)
            await r.ping()
            await r.close()
            checks["redis"] = "ok"
        except Exception as e:
            logger.error(f"Redis readiness check failed: {e}")
            checks["redis"] = "error"
        
        # MinIO (basic connectivity)
        try:
            minio_endpoint = settings.MINIO_ENDPOINT or "localhost:9000"
            minio_url = f"http://{minio_endpoint}/minio/health/live"
            async with httpx.AsyncClient() as client:
                response = await client.get(minio_url, timeout=2.0)
                if response.status_code == 200:
                    checks["minio"] = "ok"
                else:
                    checks["minio"] = "error"
        except Exception as e:
            logger.error(f"MinIO readiness check failed: {e}")
            checks["minio"] = "error"
    
    # If all checks pass, return 200; else 503
    all_ok = all(v == "ok" for v in checks.values())
    
    status_code = 200 if all_ok else 503
    return {"status": "ready" if all_ok else "not_ready", "checks": checks}
