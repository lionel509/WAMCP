from datetime import datetime, timezone
import uuid
from typing import Optional, List, Any
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index, Text, Enum, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base import Base
import enum

def utc_now():
    return datetime.now(timezone.utc)

# Enums
class ConversationType(str, enum.Enum):
    INDIVIDUAL = "individual"
    GROUP = "group"

class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"

class DocType(str, enum.Enum):
    INVOICE = "invoice"
    PDF = "pdf"
    IMAGE = "image"
    OTHER = "other"

class ExtractionStatus(str, enum.Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"

class ParticipantSource(str, enum.Enum):
    PHONE_MATCH = "phone_match"
    MANUAL = "manual"
    IMPORT = "import"
    INFERRED = "inferred"

# Models

class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[str] = mapped_column(String, default="whatsapp")
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # New safety fields
    request_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    headers_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    # conversation_id: group_id for group; derived stable key for individual
    id: Mapped[str] = mapped_column(String, primary_key=True) 
    type: Mapped[ConversationType] = mapped_column(Enum(ConversationType), nullable=False)
    business_phone_number_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Raw group ID or other external ref
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    messages = relationship("Message", back_populates="conversation")


class Participant(Base):
    __tablename__ = "participants"

    # participant_id (messages[].from)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    phone_e164: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    aliases = relationship("ParticipantAlias", back_populates="participant")
    messages = relationship("Message", back_populates="participant")


class ParticipantAlias(Base):
    __tablename__ = "participant_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    participant = relationship("Participant", back_populates="aliases")


class Message(Base):
    __tablename__ = "messages"

    # WhatsApp message_id
    id: Mapped[str] = mapped_column(String, primary_key=True) 
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    text_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_to_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Linkage to raw event (storing first seen event)
    raw_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("raw_events.id"), nullable=True)
    
    # Future-proof payload
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
    participant = relationship("Participant", back_populates="messages")
    documents = relationship("Document", back_populates="message")

    __table_args__ = (
        Index("ix_messages_conversation_sent_at", "conversation_id", "sent_at"),
        Index("ix_messages_participant_sent_at", "participant_id", "sent_at"),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType), nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    
    storage_key_raw: Mapped[str] = mapped_column(String, nullable=False)
    storage_key_sanitized: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Full text
    extracted_fields_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True) # Structured data
    
    sensitive_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    # Extraction status
    extraction_status: Mapped[ExtractionStatus] = mapped_column(Enum(ExtractionStatus), default=ExtractionStatus.PENDING)
    extraction_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    message = relationship("Message", back_populates="documents")


class Customer(Base):
    __tablename__ = "customers"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    primary_phone_e164: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    primary_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ParticipantCustomerMap(Base):
    __tablename__ = "participant_customer_map"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False) # 0.00 to 1.00
    source: Mapped[ParticipantSource] = mapped_column(Enum(ParticipantSource), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String, nullable=False) # mcp, admin, worker
    action: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    object_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True) # Full params/result stats
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WatchdogRun(Base):
    __tablename__ = "watchdog_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
