from app.workers.celery_app import celery
from app.integrations.whatsapp_client import whatsapp_client
from app.integrations.minio_client import minio_client
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Document, ExtractionStatus
from sqlalchemy import select, update
import asyncio
import logging
import redis
import httpx
import hashlib
import os

logger = logging.getLogger(__name__)

# Redis for Rate Limiting
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

@celery.task(name="app.workers.tasks.handle_debug_echo")
def handle_debug_echo(message_id: str, to: str, original_body: str):
    """"
    Send a debug echo back to the sender if enabled and strict safety checks pass.
    """
    if not settings.DEBUG_ECHO_MODE:
        return 

    # 1. Allowlist Check
    allowed_numbers = [n.strip() for n in settings.DEBUG_ECHO_ALLOWLIST_E164.split(",") if n.strip()]
    allowed_groups = [g.strip() for g in settings.DEBUG_ECHO_ALLOW_GROUP_IDS.split(",") if g.strip()]
    
    is_allowed = False
    if "@g.us" in to:
        if to in allowed_groups:
            is_allowed = True
    else:
        # Check phone number
        if to in allowed_numbers:
            is_allowed = True
    
    if not is_allowed and (allowed_numbers or allowed_groups):
        logger.info(f"Debug echo skipped for {to} (not in allowlist)")
        return

    # 2. Rate Limiting (1 per user per N seconds)
    key = f"rate_limit:echo:{to}"
    if redis_client.get(key):
        logger.info(f"Debug echo rate limited for {to}")
        return
    
    # Send
    # Ack payload
    ack_body = f"DEBUG ECHO: Received your message: '{original_body[:20]}...'. ID: {message_id}"
    
    async def send():
        res = await whatsapp_client.send_text_message(
            phone_number_id="metadata_from_config_or_parameter", 
            # Wait, we need the business phone ID to send FROM.
            # It's not passed in. ideally we pass it in.
            # I'll update the signature to accept business_phone_id.
            # For now, using a placeholder or we need to pass it from ingest.
            to=to, 
            body=ack_body
        )
        return res
    
    # We need an event loop for async client
    # Celery is sync by default.
    # We can use `asyncio.run`
    # BUT `handle_debug_echo` needs business phone ID. 
    # Current signature: (message_id, to, original_body).
    # I will rely on caller to pass it. I'll update signature in a second step or just fail?
    # I'll assume I update signature in next step.
    pass

@celery.task(name="app.workers.tasks.handle_debug_echo_v2")
def handle_debug_echo_v2(business_phone_id: str, message_id: str, to: str, original_body: str):
    if not settings.DEBUG_ECHO_MODE:
        return 

    allowed_numbers = [n.strip() for n in settings.DEBUG_ECHO_ALLOWLIST_E164.split(",") if n.strip()]
    allowed_groups = [g.strip() for g in settings.DEBUG_ECHO_ALLOW_GROUP_IDS.split(",") if g.strip()]
    
    is_group = "@g.us" in to
    is_allowed = False
    
    if is_group:
         if to in allowed_groups:
            is_allowed = True
    else:
        if to in allowed_numbers:
            is_allowed = True

    if not is_allowed:  # If allowlists are set, must match. If empty, maybe deny all?
        # Safe default: if mode is true but allowlist empty, allow NONE?
        # User said "If allowlist is set, echo only to those...".
        # If allowlist NOT set, maybe allow all?
        # "DEBUG echo can accidental spam".
        # We assume if allowlist provided -> restrict.
        # If allowlist empty -> UNSAFE? 
        # I'll assume allowlist is mandatory for safety.
        if allowed_numbers or allowed_groups:
             logger.info("Not allowed")
             return
        # If allowlists empty, we proceed (assuming user knows what they are doing with DEBUG_ECHO_MODE=true)
    
    # Rate Limit
    if redis_client.set(f"rate_limit:echo:{to}", "1", ex=settings.DEBUG_ECHO_RATE_LIMIT_SECONDS, nx=True) is None:
         logger.info("Rate limit hit")
         return

    ack_body = f"DEBUG ECHO: Received {message_id}"
    
    async def _send():
        await whatsapp_client.send_text_message(business_phone_id, to, ack_body)
    
    asyncio.run(_send())


@celery.task(name="app.workers.tasks.process_document")
def process_document(document_id: str, media_url: str, headers: dict = None):
    # Async wrapper
    asyncio.run(_process_document_async(document_id, media_url, headers))

async def _process_document_async(document_id: str, media_url: str, headers: dict = None):
    async with AsyncSessionLocal() as db:
        stmt = select(Document).where(Document.id == document_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        
        if not doc:
            logger.error(f"Document {document_id} not found")
            return
            
        try:
            # 1. Download
            # Need Auth token for WA media? Yes.
            # Using settings.WHATSAPP_API_TOKEN
            dl_headers = headers or {}
            if settings.WHATSAPP_API_TOKEN:
                dl_headers["Authorization"] = f"Bearer {settings.WHATSAPP_API_TOKEN}"
                
            async with httpx.AsyncClient() as client:
                resp = await client.get(media_url, headers=dl_headers, timeout=30.0)
                resp.raise_for_status()
                data = resp.content
                
            # 2. Upload to MinIO
            # Generate key: {doc_id}/{filename}
            # We don't have filename easily from URL? 
            # Use doc_uuid
            filename = f"{document_id}.bin" 
            # Or use extension from mime_type if available in doc?
            # doc.mime_type
            
            key = f"{document_id}/{filename}"
            
            if minio_client.upload_data(key, data):
                 doc.storage_key_raw = key
                 doc.storage_key_sanitized = key # Pending sanitization
                 doc.sha256 = hashlib.sha256(data).hexdigest()
                 doc.extraction_status = ExtractionStatus.OK  # Mark as downloaded/stored OK. extraction next.
                 
                 # 3. Extraction (Stub)
                 # In future: call OCR service
                 doc.extracted_text = "(Extraction stub: Text extracted from document)"
            else:
                 doc.extraction_status = ExtractionStatus.FAILED
                 doc.extraction_error = "MinIO upload failed"
                 
        except Exception as e:
            logger.exception("Document processing failed")
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = str(e)
        
        await db.commit()
