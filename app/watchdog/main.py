import asyncio
import logging
import json
import time
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import WatchdogRun
from app.watchdog import checks, remediation, notifications
import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("watchdog")

async def run_cycle():
    logger.info("Starting Watchdog Cycle")
    
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        async with AsyncSessionLocal() as db:
            # Checks
            dep_status = await checks.check_dependencies(db, redis_client)
            ingest_alerts = await checks.check_ingestion_health(db)
            doc_alerts, stalled_docs = await checks.check_document_health(db)
            queue_alerts = await checks.check_queue_health(redis_client)
            
            all_alerts = ingest_alerts + doc_alerts + queue_alerts
            
            # Status JSON
            status = {
                "dependencies": dep_status,
                "alerts": all_alerts,
                "stalled_docs_count": len(stalled_docs)
            }
            
            # Log Run
            # We must commit this even if notifications fail?
            run_record = WatchdogRun(status_json=status)
            db.add(run_record)
            await db.commit()
            
            # Remediation
            if stalled_docs:
                await remediation.reenqueue_stalled_documents(db, stalled_docs)
                
            # Notifications
            if all_alerts:
                for alert in all_alerts:
                    await notifications.send_alert(alert["type"], alert)
                    
            # Critical Dependency Failure Alert
            if not all(dep_status.values()):
                 await notifications.send_alert("dependency_failure", dep_status)
                 
    except Exception as e:
        logger.exception(f"Error in watchdog cycle: {e}")
    finally:
        redis_client.close()

async def main():
    if not settings.WATCHDOG_ENABLED:
        logger.info("Watchdog disabled. Exiting.")
        return

    logger.info(f"Watchdog started. Interval: {settings.WATCHDOG_INTERVAL_SECONDS}s")
    
    while True:
        start_time = time.time()
        try:
            await run_cycle()
        except Exception as e:
            logger.exception("Watchdog Cycle Crash")
        
        elapsed = time.time() - start_time
        sleep_time = max(1.0, float(settings.WATCHDOG_INTERVAL_SECONDS) - elapsed)
        await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    asyncio.run(main())
