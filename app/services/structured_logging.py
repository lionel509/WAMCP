"""
Structured logging utilities for WhatsApp webhook events.
"""
import json
import logging
from typing import Optional, Any, Dict
import uuid

logger = logging.getLogger(__name__)

class StructuredLogger:
    """Helper for consistent JSON logging of webhook events."""
    
    @staticmethod
    def log_event(event_name: str, **kwargs):
        """Log a structured event as JSON."""
        log_data = {
            "event": event_name,
            **kwargs
        }
        logger.info(json.dumps(log_data))
    
    @staticmethod
    def log_webhook_verification(success: bool, mode: Optional[str] = None, request_id: Optional[str] = None):
        """Log webhook verification attempt."""
        StructuredLogger.log_event(
            "whatsapp_webhook_verification",
            success=success,
            mode=mode,
            request_id=request_id or "unknown"
        )
    
    @staticmethod
    def log_webhook_received(
        request_id: str,
        request_hash: str,
        signature_valid: bool,
        envelope_type: str,
        messages_count: int,
        statuses_count: int,
        phone_number_id: Optional[str] = None
    ):
        """Log webhook receipt."""
        StructuredLogger.log_event(
            "whatsapp_webhook_received",
            request_id=request_id,
            request_hash=request_hash[:8],  # Truncate for readability
            signature_valid=signature_valid,
            envelope_type=envelope_type,
            messages_count=messages_count,
            statuses_count=statuses_count,
            phone_number_id=phone_number_id
        )
    
    @staticmethod
    def log_webhook_parsed(
        request_id: str,
        normalized_events_count: int,
        parse_status: str,
        parse_error: Optional[str] = None
    ):
        """Log webhook parsing result."""
        log_data = {
            "request_id": request_id,
            "normalized_events_count": normalized_events_count,
            "parse_status": parse_status
        }
        if parse_error:
            log_data["parse_error"] = parse_error
        
        StructuredLogger.log_event("whatsapp_webhook_parsed", **log_data)
    
    @staticmethod
    def log_message_normalized(
        request_id: str,
        message_id: str,
        conversation_type: str,
        conversation_id: str,
        sender_participant_id: str,
        message_type: str,
        sent_at: Optional[str] = None
    ):
        """Log message normalization."""
        StructuredLogger.log_event(
            "whatsapp_message_normalized",
            request_id=request_id,
            message_id=message_id,
            conversation_type=conversation_type,
            conversation_id=conversation_id,
            sender_participant_id=sender_participant_id,
            message_type=message_type,
            sent_at=sent_at
        )
    
    @staticmethod
    def log_message_persisted(request_id: str, message_id: str, inserted: bool):
        """Log message persistence."""
        StructuredLogger.log_event(
            "whatsapp_message_persisted",
            request_id=request_id,
            message_id=message_id,
            inserted=inserted
        )
    
    @staticmethod
    def log_webhook_error(
        request_id: str,
        error_message: str,
        exception_class: str
    ):
        """Log webhook processing error."""
        StructuredLogger.log_event(
            "whatsapp_webhook_error",
            request_id=request_id,
            error_message=error_message,
            exception_class=exception_class
        )
    
    @staticmethod
    def log_debug_echo_attempt(
        request_id: str,
        message_id: str,
        recipient: str,
        allowed: bool,
        reason: Optional[str] = None,
        success: Optional[bool] = None
    ):
        """Log debug echo attempt."""
        log_data = {
            "request_id": request_id,
            "message_id": message_id,
            "recipient": recipient,
            "allowed": allowed
        }
        if reason:
            log_data["reason"] = reason
        if success is not None:
            log_data["success"] = success
        
        StructuredLogger.log_event("debug_echo_attempt", **log_data)
