from app.workers.celery_app import celery
from app.integrations.whatsapp_client import whatsapp_client
from app.integrations.minio_client import minio_client
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Document, ExtractionStatus, DocType
from app.services.document_extraction import (
    DocumentExtractionService,
    DocumentExtractionError,
    DocumentNotFoundError,
    DocumentTooLargeError,
)
from sqlalchemy import select
import asyncio
import logging
import redis
import uuid

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
    allowed_numbers = [n.strip() for n in settings.debug_echo_allowlist_e164]
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
    logger.info(f"[TASK START] handle_debug_echo_v2 called with: business_phone_id={business_phone_id}, to={to}, original_body={original_body}")
    
    if not settings.DEBUG_ECHO_MODE:
        logger.info("Debug echo skipped (DEBUG_ECHO_MODE=false)")
        return 

    def _normalize_phone(value: str) -> str:
        # Keep digits only so allowlist entries can omit "+" or country code.
        return "".join(ch for ch in value if ch.isdigit())

    allowed_numbers = [_normalize_phone(n) for n in settings.debug_echo_allowlist_e164 if n.strip()]
    allowed_groups = [g.strip() for g in settings.debug_echo_allow_group_ids if g.strip()]
    
    is_group = "@g.us" in to
    is_allowed = False
    to_normalized = _normalize_phone(to)
    
    if is_group:
        if allowed_groups:
            is_allowed = to.strip() in allowed_groups
        else:
            is_allowed = True
    else:
        if allowed_numbers:
            for allowed in allowed_numbers:
                if to_normalized == allowed or to_normalized.endswith(allowed) or allowed.endswith(to_normalized):
                    is_allowed = True
                    break
        else:
            is_allowed = True

    if not is_allowed:
        logger.info(
            "[TASK] Debug echo skipped (not in allowlist): to=%s allow_numbers=%s allow_groups=%s",
            to,
            allowed_numbers,
            allowed_groups,
        )
        return
    
    logger.info(f"[TASK] Passed allowlist check for {to}")
    
    # Rate Limit
    if redis_client.set(f"rate_limit:echo:{to}", "1", ex=settings.DEBUG_ECHO_RATE_LIMIT_SECONDS, nx=True) is None:
        logger.info(f"[TASK] Debug echo rate limit hit for {to}")
        return

    logger.info(f"[TASK] Passed rate limit check, preparing to send echo")

    preview = (original_body or "").strip()
    if len(preview) > 256:
        preview = preview[:253] + "..."
    ack_body = f"DEBUG ECHO: {preview or '[no body]'} (id: {message_id})"
    
    async def _send():
        res = await whatsapp_client.send_text_message(business_phone_id, to, ack_body)
        return res
    
    try:
        logger.info(f"[TASK] Calling _send() for {to}")
        res = asyncio.run(_send())
        logger.info(f"[TASK] _send() returned: {res}")
        if res and "error" in res:
            logger.error(
                "[TASK] Debug echo send failed: to=%s phone_id=%s error=%s",
                to,
                business_phone_id,
                res.get("error"),
            )
        else:
            logger.info("[TASK] Debug echo sent successfully: to=%s phone_id=%s", to, business_phone_id)
    except Exception as e:
        logger.exception("[TASK] Debug echo send raised exception: to=%s phone_id=%s exception=%s", to, business_phone_id, str(e))


@celery.task(name="app.workers.tasks.process_document")
def process_document(document_id: str, media_url: str | None = None, headers: dict | None = None):
    # Async wrapper
    asyncio.run(_process_document_async(document_id, media_url, headers))

async def _process_document_async(
    document_id: str, media_url: str | None = None, headers: dict | None = None, storage_client=None
):
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except ValueError:
        logger.error(f"Invalid document id {document_id}")
        return

    async with AsyncSessionLocal() as db:
        stmt = select(Document).where(Document.id == doc_uuid)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        extractor = DocumentExtractionService(storage_client or minio_client)
        doc.extraction_status = ExtractionStatus.PENDING
        doc.extraction_error = None

        try:
            sanitized_text, fields = await extractor.process(doc, media_url, headers)
            doc.extracted_text = sanitized_text
            if doc.doc_type == DocType.INVOICE:
                doc.extracted_fields_json = fields or {}
            doc.extraction_status = ExtractionStatus.OK
            doc.extraction_error = None
        except DocumentTooLargeError as e:
            logger.warning(f"Document {doc.id} exceeded size limit: {e}")
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = "Document exceeds maximum allowed size"
        except DocumentNotFoundError as e:
            logger.error(f"Document {doc.id} missing from storage: {e}")
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = "Document not available in storage"
        except DocumentExtractionError as e:
            logger.warning(f"Extraction failed for document {doc.id}: {e}")
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = str(e)
        except Exception:
            logger.exception("Document processing failed")
            doc.extraction_status = ExtractionStatus.FAILED
            doc.extraction_error = "Unexpected extraction failure"
        
        await db.commit()
