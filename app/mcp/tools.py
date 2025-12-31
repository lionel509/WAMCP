from typing import List, Optional, Dict, Any
from sqlalchemy.future import select
from sqlalchemy import or_, desc, func, text
from app.db.session import AsyncSessionLocal
from app.db.models import Conversation, Message, Document, AuditLog
import logging
import json
import uuid

logger = logging.getLogger(__name__)

async def audit_tool_call(tool_name: str, params: dict, result_scope: dict):
    """
    Log MCP tool execution to AuditLog.
    """
    async with AsyncSessionLocal() as db:
        log_entry = AuditLog(
            actor="mcp",
            action=tool_name,
            metadata_json={
                "params": params,
                "scope": result_scope
            }
        )
        db.add(log_entry)
        await db.commit()


async def list_conversations(limit: int = 10, offset: int = 0):
    async with AsyncSessionLocal() as db:
        stmt = select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit).offset(offset)
        result = await db.execute(stmt)
        conversations = result.scalars().all()
        
        data = []
        sources = []
        scope_ids = []
        
        for c in conversations:
            data.append({
                "id": c.id,
                "type": c.type.value,
                "name": c.display_name or c.id,
                "updated_at": c.updated_at.isoformat()
            })
            sources.append({"type": "conversation", "id": c.id})
            scope_ids.append(c.id)
            
        res = {
            "data": data,
            "sources": sources,
            "scope": {"conversation_ids": scope_ids}
        }
        
        await audit_tool_call("list_conversations", {"limit": limit, "offset": offset}, res["scope"])
        return res

async def get_recent_messages(conversation_id: str, limit: int = 20):
    async with AsyncSessionLocal() as db:
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(desc(Message.sent_at)).limit(limit)
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        # Determine strict citation requirements
        # We return citation for EACH message? 
        # Or aggregation?
        # User: "return ... sources[] citations (message IDs, timestamps...)"
        
        data = []
        sources = []
        
        for m in messages:
            msg_data = {
                "id": m.id,
                "sender": m.participant_id,
                "direction": m.direction,
                "type": m.message_type,
                "timestamp": m.sent_at.isoformat(),
                "text": m.text_body
            }
            if m.payload_json:
                 msg_data["metadata"] = "Available in payload"
                 
            data.append(msg_data)
            sources.append({
                "type": "message", 
                "id": m.id, 
                "timestamp": m.sent_at.isoformat()
            })
            
        res = {
            "data": data, # Return detailed list as data
            "sources": sources, # Citations
            "scope": {"conversation_id": conversation_id, "message_ids": [m.id for m in messages]}
        }
        
        await audit_tool_call("get_recent_messages", {"conversation_id": conversation_id, "limit": limit}, res["scope"])
        return res

async def search_messages(query: str, limit: int = 50, conversation_id: Optional[str] = None):
    async with AsyncSessionLocal() as db:
        # Simple ILIKE search for now.
        # FTS would be:
        # stmt = select(Message).where(Message.text_body.match(query))
        # But we need tsvector configuration.
        # Fallback to ILIKE for MVP safety.
        
        filters = [Message.text_body.ilike(f"%{query}%")]
        if conversation_id:
            filters.append(Message.conversation_id == conversation_id)
            
        stmt = select(Message).where(*filters).order_by(desc(Message.sent_at)).limit(limit)
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        data = []
        sources = []
        
        for m in messages:
            data.append({
                "id": m.id,
                "conversation_id": m.conversation_id,
                "text": m.text_body,
                "timestamp": m.sent_at.isoformat()
            })
            sources.append({"type": "message", "id": m.id})
            
        res = {
            "data": data,
            "sources": sources,
            "scope": {"query": query, "hit_count": len(messages)}
        }
        
        await audit_tool_call("search_messages", {"query": query, "limit": limit}, res["scope"])
        return res

async def list_documents(limit: int = 20):
    async with AsyncSessionLocal() as db:
        stmt = select(Document).order_by(desc(Document.created_at)).limit(limit)
        result = await db.execute(stmt)
        docs = result.scalars().all()
        
        data = []
        sources = []
        ids = []
        
        for d in docs:
            data.append({
                "id": str(d.id),
                "type": d.doc_type.value,
                "mime": d.mime_type,
                "status": d.extraction_status,
                "created_at": d.created_at.isoformat()
            })
            sources.append({"type": "document", "id": str(d.id)})
            ids.append(str(d.id))
            
        res = {
            "data": data,
            "sources": sources,
            "scope": {"document_ids": ids}
        }
        
        await audit_tool_call("list_documents", {"limit": limit}, res["scope"])
        return res
