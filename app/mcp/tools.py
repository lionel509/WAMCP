import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select, text

from app.config import settings
from app.db.models import AuditLog, Conversation, Document, Message
from app.db.session import AsyncSessionLocal, get_audit_db

logger = logging.getLogger(__name__)


def _permalink(kind: str, resource_id: str, conversation_id: Optional[str] = None) -> Optional[str]:
    base = settings.public_base_url
    if not base:
        return None

    if kind == "conversation":
        return f"{base}/admin/conversations/{resource_id}"
    if kind == "message" and conversation_id:
        return f"{base}/admin/conversations/{conversation_id}/messages"
    if kind == "document":
        return f"{base}/admin/documents/{resource_id}"
    return None


def _source(kind: str, resource_id: str, conversation_id: Optional[str] = None, ts: Optional[str] = None) -> Dict[str, Any]:
    src: Dict[str, Any] = {"kind": kind, "id": resource_id}
    if conversation_id:
        src["conversation_id"] = conversation_id
    if ts:
        src["ts"] = ts
    permalink = _permalink(kind, resource_id, conversation_id)
    if permalink:
        src["permalink"] = permalink
    return src


async def audit_tool_call(tool_name: str, params: dict, result_scope: dict):
    """
    Log MCP tool execution to AuditLog (audit DB if configured, otherwise log).
    """
    async with get_audit_db() as audit_db:
        if audit_db is None:
            logger.info("audit_log (tool=%s): %s", tool_name, {"params": params, "scope": result_scope})
            return

        try:
            log_entry = AuditLog(actor="mcp", action=tool_name, metadata_json={"params": params, "scope": result_scope})
            audit_db.add(log_entry)
            await audit_db.commit()
        except Exception:
            logger.warning("Failed to write MCP audit log", exc_info=True)


async def list_conversations(limit: int = 10, offset: int = 0):
    async with AsyncSessionLocal() as db:
        if settings.plugin_mode:
            await db.execute(text("SET default_transaction_read_only = on"))

        stmt = select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit).offset(offset)
        result = await db.execute(stmt)
        conversations = result.scalars().all()

        data = []
        sources = []
        scope_ids = []

        for c in conversations:
            updated = c.updated_at.isoformat() if c.updated_at else None
            data.append(
                {
                    "id": c.id,
                    "type": c.type.value,
                    "name": c.display_name or c.id,
                    "updated_at": updated,
                }
            )
            sources.append(_source("conversation", c.id, conversation_id=c.id, ts=updated))
            scope_ids.append(c.id)

        res = {"data": data, "sources": sources, "scope": {"conversation_ids": scope_ids, "limit": limit, "offset": offset}}

        await audit_tool_call("list_conversations", {"limit": limit, "offset": offset}, res["scope"])
        return res


async def get_recent_messages(conversation_id: str, limit: int = 20):
    async with AsyncSessionLocal() as db:
        if settings.plugin_mode:
            await db.execute(text("SET default_transaction_read_only = on"))

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.sent_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()

        data = []
        sources = []

        for m in messages:
            timestamp = m.sent_at.isoformat() if m.sent_at else None
            msg_data = {
                "id": m.id,
                "sender": m.participant_id,
                "direction": m.direction.value if hasattr(m.direction, "value") else m.direction,
                "type": m.message_type,
                "timestamp": timestamp,
                "text": m.text_body,
            }
            if m.payload_json:
                msg_data["metadata"] = "Available in payload"

            data.append(msg_data)
            sources.append(_source("message", m.id, conversation_id=conversation_id, ts=timestamp))

        res = {
            "data": data,
            "sources": sources,
            "scope": {"conversation_id": conversation_id, "message_ids": [m.id for m in messages]},
        }

        await audit_tool_call("get_recent_messages", {"conversation_id": conversation_id, "limit": limit}, res["scope"])
        return res


async def search_messages(query: str, limit: int = 50, conversation_id: Optional[str] = None):
    async with AsyncSessionLocal() as db:
        if settings.plugin_mode:
            await db.execute(text("SET default_transaction_read_only = on"))

        filters: List[Any] = [Message.text_body.ilike(f"%{query}%")]
        if conversation_id:
            filters.append(Message.conversation_id == conversation_id)

        stmt = select(Message).where(*filters).order_by(desc(Message.sent_at)).limit(limit)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        data = []
        sources = []

        for m in messages:
            ts_val = m.sent_at.isoformat() if m.sent_at else None
            data.append(
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id,
                    "text": m.text_body,
                    "timestamp": ts_val,
                }
            )
            sources.append(_source("message", m.id, conversation_id=m.conversation_id, ts=ts_val))

        res = {
            "data": data,
            "sources": sources,
            "scope": {
                "query": query,
                "conversation_id": conversation_id,
                "message_ids": [m.id for m in messages],
                "count": len(messages),
            },
        }

        await audit_tool_call("search_messages", {"query": query, "limit": limit, "conversation_id": conversation_id}, res["scope"])
        return res


async def list_documents(limit: int = 20):
    async with AsyncSessionLocal() as db:
        if settings.plugin_mode:
            await db.execute(text("SET default_transaction_read_only = on"))

        stmt = (
            select(Document, Message.conversation_id, Message.sent_at)
            .join(Message, Document.message_id == Message.id, isouter=True)
            .order_by(desc(Document.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()

        data = []
        sources = []
        ids = []
        conversation_ids: List[str] = []
        message_ids: List[str] = []

        for doc, conv_id, sent_at in rows:
            created_at = doc.created_at.isoformat() if doc.created_at else None
            doc_id = str(doc.id)
            data.append(
                {
                    "id": doc_id,
                    "message_id": doc.message_id,
                    "type": doc.doc_type.value,
                    "mime": doc.mime_type,
                    "status": doc.extraction_status.value,
                    "created_at": created_at,
                    "conversation_id": conv_id,
                }
            )
            ids.append(doc_id)
            if conv_id:
                conversation_ids.append(conv_id)
            if doc.message_id:
                message_ids.append(doc.message_id)
            ts_val = sent_at.isoformat() if sent_at else created_at
            sources.append(_source("document", doc_id, conversation_id=conv_id, ts=ts_val))

        res = {
            "data": data,
            "sources": sources,
            "scope": {
                "document_ids": ids,
                "conversation_ids": conversation_ids,
                "message_ids": message_ids,
            },
        }

        await audit_tool_call("list_documents", {"limit": limit}, res["scope"])
        return res
