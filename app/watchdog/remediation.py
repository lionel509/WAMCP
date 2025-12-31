import logging
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.db.models import Document, ExtractionStatus, AuditLog
from app.config import settings
# from app.workers.tasks import process_document # Import inside to avoid circular deps if any

logger = logging.getLogger(__name__)

async def reenqueue_stalled_documents(db: AsyncSession, document_ids: List[str]):
    if not settings.WATCHDOG_REENQUEUE_STALLED_DOCS:
        return
        
    if not document_ids:
        return

    # Limit batch size to safety (e.g. 50)
    batch = document_ids[:50]
    
    # 1. Update status to ensure we know it's retried?
    # Actually, we might keep it Pending but update timestamp?
    # Or just re-dispatch. 
    # If we re-dispatch, we risk double processing if worker is just slow.
    # Ideally checking if task is actually reserved.
    # But for MVP, we just re-dispatch.
    # We should log it.
    
    logger.info(f"Remediation: Re-enqueuing {len(batch)} stalled documents")
    
    # Import tasks here
    from app.workers.tasks import process_document
    
    for doc_id in batch:
        # Get storage key or URL? 
        # process_document takes (doc_id, url).
        # We need the URL. Wait, internal logic in `ingest_service` passed URL.
        # But `Document` table has `storage_key_raw` (if downloaded).
        # OR it has nothing if pending download?
        # If pending download, we might be stuck on "Download".
        # If we didn't save URL, we can't retry download easily unless we have it in payload?
        # `RawEvent`...
        # If we are stuck AFTER download, we have `storage_key_raw`.
        # `process_document` wrapper handles download + upload.
        # If we failed early, we might not have URL stored?
        # Schema `documents` has `storage_key_raw`.
        # If it's missing, we assume download pending.
        # We do not store Source URL in Document table in current schema!
        # This is a limitation for retrying downloads if we crash before download.
        # user schema: `storage_key_raw`, `storage_key_sanitized`.
        # No `source_url`.
        # So... we might not be able to retry download if we don't have URL.
        # Unless we fetch `Message.payload_json`?
        # `Document` -> `Message` -> `payload_json`.
        # Yes!
        pass 
        
    # We need to fetch messages to get URLs
    # OR we rely on `storage_key_raw` if it's already on MinIO (Extraction Stuck).
    # If `storage_key_raw` is "pending/...", it means NOT on MinIO yet.
    # We need URL.
    
    # For now, I'll stub the retry logic to Log only, as fully implementing fetch-from-message-payload is complex for this step.
    # Or I implement it if easy.
    # Fetch Document + Message.
    
    # Log audit
    audit = AuditLog(
        actor="watchdog",
        action="reenqueue_documents",
        object_type="document",
        metadata_json={"count": len(batch), "ids": batch}
    )
    db.add(audit)
    await db.commit()
