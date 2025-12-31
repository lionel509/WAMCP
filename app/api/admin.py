import logging
import subprocess
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AuditLog, Conversation, Document, Message
from app.db.session import get_db
from app.integrations.minio_client import minio_client

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


async def require_admin_api_key(x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-Api-Key")):
    if not x_admin_api_key:
        raise HTTPException(status_code=401, detail="Missing admin API key")
    if x_admin_api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return True


async def log_admin_action(db: AsyncSession, endpoint: str, params: Dict[str, Any]):
    try:
        audit = AuditLog(
            actor="admin_api",
            action="read",
            object_type="admin_endpoint",
            metadata_json={"endpoint": endpoint, "params": params},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        logger.warning("Failed to write admin audit log", exc_info=True)


def _git_version() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


@router.get("/health")
async def admin_health(
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    status = {"postgres": False, "redis": False, "minio": False}

    try:
        await db.execute(text("SELECT 1"))
        status["postgres"] = True
    except Exception:
        status["postgres"] = False

    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        status["redis"] = bool(redis_client.ping())
    except Exception:
        status["redis"] = False
    finally:
        try:
            redis_client.close()
        except Exception:
            pass

    try:
        status["minio"] = minio_client.client.bucket_exists(minio_client.bucket)
    except Exception:
        status["minio"] = False

    version = _git_version()
    response = {"dependencies": status, "version": version, "env": settings.APP_ENV}

    await log_admin_action(db, "/admin/health", {})
    return response


@router.get("/conversations")
async def list_conversations(
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit).offset(offset)
    res = await db.execute(stmt)
    conversations = res.scalars().all()

    payload = [
        {
            "id": c.id,
            "type": c.type.value,
            "display_name": c.display_name,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in conversations
    ]

    await log_admin_action(db, "/admin/conversations", {"limit": limit, "offset": offset})
    return {"conversations": payload}


@router.get("/conversations/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: str,
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    before_ts: Optional[str] = Query(None, alias="before_ts"),
):
    stmt = select(Message).where(Message.conversation_id == conversation_id)

    if before_ts:
        try:
            cutoff = datetime.fromisoformat(before_ts)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid timestamp format")
        stmt = stmt.where(Message.sent_at < cutoff)

    stmt = stmt.order_by(desc(Message.sent_at)).limit(limit)
    res = await db.execute(stmt)
    messages = res.scalars().all()

    payload = [
        {
            "id": m.id,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "text_body": m.text_body,
            "direction": m.direction.value,
            "message_type": m.message_type,
        }
        for m in messages
    ]

    await log_admin_action(
        db,
        f"/admin/conversations/{conversation_id}/messages",
        {"limit": limit, "before_ts": before_ts, "conversation_id": conversation_id},
    )
    return {"messages": payload}


@router.get("/search/messages")
async def search_messages(
    q: str,
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
    conversation_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    params = {"q": q, "conversation_id": conversation_id, "limit": limit}
    results = []
    stmt = None

    try:
        tsvector = func.to_tsvector("english", func.coalesce(Message.text_body, ""))
        tsquery = func.plainto_tsquery("english", q)
        stmt = select(Message).where(tsvector.op("@@")(tsquery))
        if conversation_id:
            stmt = stmt.where(Message.conversation_id == conversation_id)
    except Exception:
        stmt = select(Message).where(Message.text_body.ilike(f"%{q}%"))
        if conversation_id:
            stmt = stmt.where(Message.conversation_id == conversation_id)

    stmt = stmt.order_by(desc(Message.sent_at)).limit(limit)
    res = await db.execute(stmt)
    messages = res.scalars().all()

    for m in messages:
        results.append(
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "text_body": m.text_body,
            }
        )

    await log_admin_action(db, "/admin/search/messages", params)
    return {"messages": results}


@router.get("/documents")
async def list_documents(
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
    conversation_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    stmt = select(Document)
    if conversation_id:
        stmt = stmt.join(Message).where(Message.conversation_id == conversation_id)
    stmt = stmt.order_by(desc(Document.created_at)).limit(limit)

    res = await db.execute(stmt)
    documents = res.scalars().all()

    payload = [
        {
            "id": str(d.id),
            "message_id": d.message_id,
            "doc_type": d.doc_type.value,
            "mime_type": d.mime_type,
            "extraction_status": d.extraction_status.value,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in documents
    ]

    await log_admin_action(db, "/admin/documents", {"conversation_id": conversation_id, "limit": limit})
    return {"documents": payload}


@router.get("/documents/{document_id}")
async def get_document_detail(
    document_id: str,
    authorized: bool = Depends(require_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document id")

    stmt = select(Document).where(Document.id == doc_uuid)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = {
        "id": str(document.id),
        "message_id": document.message_id,
        "doc_type": document.doc_type.value,
        "mime_type": document.mime_type,
        "extraction_status": document.extraction_status.value,
        "extraction_error": document.extraction_error,
        "extracted_text": document.extracted_text or "",
        "extracted_fields": document.extracted_fields_json or {},
    }

    await log_admin_action(db, f"/admin/documents/{document_id}", {"document_id": document_id})
    return payload
