import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.config import settings
from app.db.models import (
    RawEvent,
    Conversation,
    Participant,
    ParticipantAlias,
    Message,
    ConversationType,
    MessageDirection,
    ParticipantSource,
    ParticipantCustomerMap,
    Document,
    DocType,
    ExtractionStatus,
)
from app.services.whatsapp_parser import parse_webhook_payload, NormalizedEvent
from app.security.webhook_verify import verify_signature
from app.services.structured_logging import StructuredLogger

logger = logging.getLogger(__name__)

class IngestService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_webhook(self, raw_body: bytes, headers: dict, request_id: str = None) -> Dict[str, Any]:
        """
        Process inbound webhook.
        1. Calculate Hash & Check Idempotency
        2. Verify Signature
        3. Store Raw Event
        4. Parse & Upsert Entities
        """
        if settings.plugin_mode:
            logger.warning("Webhook ingestion attempted while plugin mode is enabled; rejecting request.")
            raise HTTPException(status_code=403, detail="Webhook ingestion is disabled in plugin mode")

        if not request_id:
            request_id = str(uuid.uuid4())
        
        request_hash = hashlib.sha256(raw_body).hexdigest()
        
        # 1. Signature Verification (First Defense)
        sig_valid = True
        if settings.verify_webhook_signature:
            sig_header = headers.get("x-hub-signature-256", "")
            sig_valid = verify_signature(raw_body, sig_header, settings.whatsapp_app_secret or "")
            if not sig_valid:
                # Strictly reject if verification fails
                logger.warning(f"Signature verification failed. request_id={request_id}, hash={request_hash[:8]}")
                raise HTTPException(status_code=401, detail="Invalid Signature")

        # 2. Idempotency Check
        stmt = select(RawEvent).where(RawEvent.request_hash == request_hash)
        result = await self.db.execute(stmt)
        existing_event = result.scalar_one_or_none()
        
        if existing_event:
            logger.info(f"Duplicate webhook event ignored. request_id={request_id}, hash={request_hash[:8]}")
            return {"status": "ignored", "reason": "duplicate_event", "id": str(existing_event.id)}

        try:
            payload_json = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON body. request_id={request_id}")
            StructuredLogger.log_webhook_error(request_id, "Invalid JSON body", "JSONDecodeError")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Determine envelope type
        envelope_type = "unknown"
        messages_count = 0
        statuses_count = 0
        phone_number_id = None
        
        if "entry" in payload_json:
            envelope_type = "enveloped"
            for entry in payload_json.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages_count += len(value.get("messages", []))
                    statuses_count += len(value.get("statuses", []))
                    if not phone_number_id and "metadata" in value:
                        phone_number_id = value["metadata"].get("phone_number_id")
        else:
            envelope_type = "unwrapped"
            messages_count = len(payload_json.get("messages", []))
            statuses_count = len(payload_json.get("statuses", []))
            phone_number_id = payload_json.get("metadata", {}).get("phone_number_id")
        
        StructuredLogger.log_webhook_received(
            request_id=request_id,
            request_hash=request_hash,
            signature_valid=sig_valid,
            envelope_type=envelope_type,
            messages_count=messages_count,
            statuses_count=statuses_count,
            phone_number_id=phone_number_id
        )

        # 3. Store Raw Event
        raw_event = RawEvent(
            id=uuid.uuid4(),
            source="whatsapp",
            signature_valid=sig_valid,
            request_hash=request_hash,
            headers_json=headers,
            payload_json=payload_json
        )
        self.db.add(raw_event)
        

        # 4. Parse & Normalize
        try:
            normalized_events = parse_webhook_payload(payload_json)
        except Exception as e:
            logger.error(f"Failed to parse webhook payload: {str(e)}", exc_info=True)
            StructuredLogger.log_webhook_parsed(
                request_id=request_id,
                normalized_events_count=0,
                parse_status="failed",
                parse_error=str(e)[:100]
            )
            await self.db.commit()
            return {"status": "parse_failed", "error": str(e)[:100], "raw_event_id": str(raw_event.id)}
        
        StructuredLogger.log_webhook_parsed(
            request_id=request_id,
            normalized_events_count=len(normalized_events),
            parse_status="ok"
        )
        
        processed_messages = []
        
        for event in normalized_events:
            if event.message_id:
                await self._process_normalized_event(event, raw_event.id, request_id)
                processed_messages.append(event.message_id)

        await self.db.commit()
        return {"status": "processed", "count": len(processed_messages), "raw_event_id": str(raw_event.id)}

    async def _process_normalized_event(self, event: NormalizedEvent, raw_event_id: uuid.UUID, request_id: str = None):
        if not request_id:
            request_id = "unknown"
        
        # Log normalized event
        StructuredLogger.log_message_normalized(
            request_id=request_id,
            message_id=event.message_id or "unknown",
            conversation_type=event.conversation_type,
            conversation_id=event.conversation_id,
            sender_participant_id=event.sender_participant_id or "unknown",
            message_type=event.message_type,
            sent_at=event.timestamp.isoformat() if event.timestamp else None
        )
        
        stmt = select(Conversation).where(Conversation.id == event.conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            timestamp = event.timestamp
            conversation = Conversation(
                id=event.conversation_id,
                type=ConversationType(event.conversation_type),
                business_phone_number_id=event.business_phone_number_id,
                created_at=timestamp,
                updated_at=timestamp
            )
            self.db.add(conversation)
            # We flush to ensure it exists for FK
            # But duplicate insert might happen if race condition.
            # Catch DB error?
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                # Re-fetch
                result = await self.db.execute(stmt)
                conversation = result.scalar_one_or_none()
        
        # B. Upsert Participant (if sender present)
        if event.sender_participant_id:
            p_stmt = select(Participant).where(Participant.id == event.sender_participant_id)
            p_result = await self.db.execute(p_stmt)
            participant = p_result.scalar_one_or_none()
            
            if not participant:
                participant = Participant(
                    id=event.sender_participant_id,
                    phone_e164=event.sender_participant_id, # Assuming ID is phone for WA
                    created_at=event.timestamp,
                    updated_at=event.timestamp
                )
                self.db.add(participant)
                try:
                    await self.db.flush()
                except IntegrityError:
                    await self.db.rollback()
                    p_result = await self.db.execute(p_stmt)
                    participant = p_result.scalar_one_or_none()
            
            # C. Upsert Alias (if display name present)
            if event.sender_display_name:
                # Check if alias recorded recently? Or just simplistic upsert?
                # Requirement: "Never assume display name is stable; store alias history."
                # We check if (participant_id, name) exists.
                # Actually, unique constraint is not on name.
                # We'll search for this name for this participant.
                alias_stmt = select(ParticipantAlias).where(
                    ParticipantAlias.participant_id == participant.id,
                    ParticipantAlias.display_name == event.sender_display_name
                )
                alias_res = await self.db.execute(alias_stmt)
                alias = alias_res.scalar_one_or_none()
                
                if alias:
                    alias.last_seen_at = event.timestamp
                else:
                    alias = ParticipantAlias(
                        id=uuid.uuid4(),
                        participant_id=participant.id,
                        display_name=event.sender_display_name,
                        first_seen_at=event.timestamp,
                        last_seen_at=event.timestamp
                    )
                    self.db.add(alias)

        # D. Insert Message (Idempotent)
        # Note: Status checks usually update existing message OR insert a status record?
        # The schema `messages` table seems to store "messages".
        # Status "updates" often refer to an existing message.
        # But `messages` table has `id` which is WA Message ID.
        # IF it's an inbound message, we insert.
        # IF it's a status update, we usually update a `status` field on the message or log to a separate table.
        # However, the user schema didn't fully specify a "message_statuses" table, only "messages".
        # And normalized event has `message_id`.
        # If this is a STATUS update (sent/delivered/read), we might need to find the message and update it?
        # OR the user schema for `messages` captures *inbound* and *outbound*.
        # If it's a status update for a message we sent, the message should exist (created when we sent it).
        # But if we sent it via some other tool, it might not be in DB?
        # User said: "For each status event... normalize to message_id, status...".
        # But in schema: `messages` has `message_type`, `text_body`.
        # Does the user want status Updates stored in `messages` table?
        # NO, `messages` table PK is `id`. One row per message ID.
        # So we only insert if it's a NEW message entity.
        # Status updates are transient states of a key.
        # Re-reading Schema: `messages` does not have a "status" column!
        # It has `direction`, `sent_at`, `message_type`.
        # WHERE DO STATUSES GO?
        # User prompt: "For each status event ... normalize to ... conversation_id ... timestamp"
        # "Validation rules: ... "
        # It doesn't explicitly say where to store statuses.
        # But `RawEvent` stores everything.
        # Maybe we don't store "status updates" in a dedicated table other than `RawEvent`?
        # OR we are missing a `message_statuses` table?
        # "messages" table has `id`.
        # If I receive a text message, I insert into `messages`.
        # If I receive a "read" status for that message, do I update `messages`?
        # There is no `status` column in `messages` schema provided by user!
        # "4.1 Tables ... messages ... message_type ... text_body ..."
        # Wait, maybe I missed it.
        # "4.1 Tables ... messages ... id, conversation_id ... message_type ... text_body ..."
        # NO status column.
        # So where do status updates go?
        # Maybe `AuditLog`? Or just `RawEvent` is enough?
        # Or maybe the user implies I should have added a status column or table?
        # But they gave a specific schema.
        # "database schema ... messages ... no status column"
        # OK, I will assume for now we Only ingest "Messages" (type=text/image etc) into `messages` table.
        # Status events (sent/delivered) might be used to update `conversation` updated_at?
        # Or just logged.
        # I will Log them and maybe update `messages` if I can find where to put it.
        # Actually, looking at `messages` schema again... `direction`.
        # If I receive an OUTBOUND message status, I might not have the message in DB if I didn't send it via this system.
        # If I did, it's there.
        # The user's prompt section 3.1 says "Canonical normalized event structure ... For each status event ...".
        # But section 4 (Schema) doesn't have a place for it.
        # I'll stick to inserting *Inbound* messages into `Message` table.
        # I'll enable the logic to insert `Message` only if `text_body` or `message_type` is present and it's not a status update event?
        # NormalizedEvent has `status` field. If `status` is present, it's a status update.
        # If `status` is None, it's a message.
        
        if event.status:
            # It's a status update.
            # We currently don't have a table for statuses in the spec.
            # user spec: "Parse ... to normalized events".
            # "Ingest service (store raw -> normalize -> upsert entities)"
            # Maybe the user expects us to create a table?
            # but user listed specific tables.
            # "Strict: Each table gets its own migration..."
            # I'll just skip inserting into `messages` for status updates, 
            # effectively just logging them in `RawEvent`.
            # I'll log info.
            # Wait, `messages.message_type` could be 'status'? No, direction is 'inbound'/'outbound'.
            pass
        else:
            # It's a message content (inbound usually).
            m_stmt = select(Message).where(Message.id == event.message_id)
            m_result = await self.db.execute(m_stmt)
            existing_message = m_result.scalar_one_or_none()
            
            if not existing_message:
                # Dedupe check (user recommendation 2): "insert with ignore if exists"
                # We already checked.
                new_msg = Message(
                    id=event.message_id,
                    conversation_id=conversation.id,
                    participant_id=event.sender_participant_id, # Must exist
                    direction=MessageDirection(event.direction),
                    sent_at=event.timestamp,
                    message_type=event.message_type or "unknown",
                    text_body=event.text_body,
                    reply_to_message_id=event.reply_to_message_id,
                    raw_event_id=raw_event_id,
                    payload_json=event.raw_message_json
                )
                self.db.add(new_msg)
                
                # Log message persistence
                StructuredLogger.log_message_persisted(request_id, event.message_id, inserted=True)
                # If message_type is image/document/audio/video, we create Document entry?
                # User schema: `documents` table. `doc_type`, `storage_key_raw`, etc.
                # If the payload has media, we should kick off extraction.
                # NormalizedEvent doesn't explicitly expose media fields yet in my parser :)
                # I should update NormalizedEvent to include media info or check `raw_message_json`.
                # For MVP, per plan "Implement Document processing stub".
                # I'll inspect `raw_message_json` here for now.
                
                
                # Check for documents/media
                if event.message_type in ["image", "document", "audio", "video", "sticker"]:
                     mime_type = "application/octet-stream"
                     if event.raw_message_json:
                         media_section = event.raw_message_json.get(event.message_type, {})
                         mime_type = media_section.get("mime_type", mime_type)

                     doc_type = DocType.OTHER
                     if event.message_type == "image":
                         doc_type = DocType.IMAGE
                     elif event.message_type == "document":
                         doc_type = DocType.PDF if mime_type.startswith("application/pdf") else DocType.OTHER

                     new_doc = Document(
                         id=uuid.uuid4(),
                         message_id=new_msg.id,
                         doc_type=doc_type,
                         mime_type=mime_type,
                         storage_key_raw=f"pending/{new_msg.id}",
                         extraction_status=ExtractionStatus.PENDING
                     )
                     self.db.add(new_doc)
                     # Media download URLs are not present in normalized events; dispatch occurs once raw objects are persisted.
                
                # Enqueue Tasks
                if event.direction == "inbound" and settings.debug_echo_mode:
                     logger.info(f"Queueing debug echo task for message_id={new_msg.id}, to={new_msg.participant_id}")
                     from app.workers.tasks import handle_debug_echo_v2
                     handle_debug_echo_v2.delay(
                         business_phone_id=event.business_phone_number_id,
                         message_id=new_msg.id,
                         to=new_msg.participant_id,
                         original_body=new_msg.text_body or "[Media]"
                     )
                     logger.info(f"Debug echo task queued successfully")
            else:
                # Message already exists
                StructuredLogger.log_message_persisted(request_id, event.message_id, inserted=False)

        return
