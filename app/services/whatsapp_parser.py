from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

# Internal normalized structures

class NormalizedEvent(BaseModel):
    # Common
    message_id: str
    conversation_id: str
    conversation_type: str # individual | group
    business_phone_number_id: str
    business_display_phone_number: Optional[str] = None
    timestamp: datetime
    
    # Message specific
    sender_participant_id: Optional[str] = None # phone number
    sender_contact_wa_id: Optional[str] = None
    sender_display_name: Optional[str] = None
    direction: str = "inbound" # inbound | outbound (status is usually outbound update)
    message_type: Optional[str] = None
    text_body: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    
    # Status specific
    status: Optional[str] = None # sent, delivered, read, failed
    
    # Errors
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Raw payload reference (for debugging/storage if needed)
    raw_message_json: Optional[Dict[str, Any]] = None


def parse_webhook_payload(payload: Dict[str, Any]) -> List[NormalizedEvent]:
    """
    Parses a WhatsApp Webhook payload (Enveloped or Unwrapped) into a list of NormalizedEvents.
    """
    events: List[NormalizedEvent] = []
    
    # 1. Identify structure
    # Unwrapped n8n style: top level has "messages" or "statuses" field, and "contacts"
    if "messages" in payload or "statuses" in payload:
        # It's an unwrapped value object
        # But wait, n8n style usually has 'metadata' at top level too.
        # Let's treat it as a single 'value' object extract.
        events.extend(_parse_value_object(payload))
        return events
        
    # Standard Enveloped: object -> entry[] -> changes[] -> value
    if payload.get("object") == "whatsapp_business_account":
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value")
                if value:
                    events.extend(_parse_value_object(value))
    
    return events


def _parse_value_object(value: Dict[str, Any]) -> List[NormalizedEvent]:
    events: List[NormalizedEvent] = []
    
    metadata = value.get("metadata", {})
    biz_phone_id = metadata.get("phone_number_id", "")
    biz_display_phone = metadata.get("display_phone_number")
    
    # Contacts map: wa_id -> profile.name
    contacts_map = {}
    for contact in value.get("contacts", []):
        wa_id = contact.get("wa_id")
        name = contact.get("profile", {}).get("name")
        if wa_id:
            contacts_map[wa_id] = name

    # 1. Parse Messages
    if "messages" in value:
        for msg in value["messages"]:
            events.append(_normalize_message(msg, biz_phone_id, biz_display_phone, contacts_map))
            
    # 2. Parse Statuses
    if "statuses" in value:
        for status in value["statuses"]:
            events.append(_normalize_status(status, biz_phone_id, biz_display_phone))
            
    return events


def _normalize_message(
    msg: Dict[str, Any], 
    biz_phone_id: str, 
    biz_display_phone: Optional[str],
    contacts_map: Dict[str, str]
) -> NormalizedEvent:
    
    msg_id = msg.get("id", "") # Mandatory
    participant_id = msg.get("from", "") # Sender phone
    timestamp_str = msg.get("timestamp")
    timestamp = datetime.fromtimestamp(int(timestamp_str)) if timestamp_str else datetime.now(timezone.utc)
    
    msg_type = msg.get("type", "unknown")
    text_body = None
    if msg_type == "text":
        text_body = msg.get("text", {}).get("body")
    
    # Conversation Logic
    group_id = msg.get("group_id")
    context = msg.get("context", {})
    reply_to_id = context.get("id") # Reply to message ID
    # Note: context might also have group_id but top level is safer
    
    if group_id:
        conversation_type = "group"
        conversation_id = group_id
    else:
        conversation_type = "individual"
        # Derived stable key: biz_phone_id : participant_id
        conversation_id = f"{biz_phone_id}:{participant_id}"

    # Sender info
    sender_name = contacts_map.get(participant_id)
    
    errors = []
    if msg_type == "unsupported":
        errors = msg.get("errors", [])

    return NormalizedEvent(
        message_id=msg_id,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        business_phone_number_id=biz_phone_id,
        business_display_phone_number=biz_display_phone,
        timestamp=timestamp,
        sender_participant_id=participant_id,
        sender_contact_wa_id=participant_id, # Usually same as from
        sender_display_name=sender_name,
        direction="inbound", # Always inbound for messages in webhook
        message_type=msg_type,
        text_body=text_body,
        reply_to_message_id=reply_to_id,
        errors=errors,
        raw_message_json=msg
    )


def _normalize_status(
    status: Dict[str, Any],
    biz_phone_id: str,
    biz_display_phone: Optional[str]
) -> NormalizedEvent:
    
    msg_id = status.get("id", "")
    status_val = status.get("status")
    timestamp_str = status.get("timestamp")
    timestamp = datetime.fromtimestamp(int(timestamp_str)) if timestamp_str else datetime.now(timezone.utc)
    recipient_id = status.get("recipient_id", "")
    
    # Statuses usually indicate OUTBOUND message state
    recip_type = status.get("recipient_type") # "group" or "individual" (implied)
    
    # NOTE: Meta documentation says `recipient_id` is the user WAID or Group ID.
    
    if recip_type == "group":
        conversation_type = "group"
        conversation_id = recipient_id # Group ID
    else:
        conversation_type = "individual"
        # For status, recipient_id is the user we sent to.
        # Stable key: biz_phone_id : recipient_id
        conversation_id = f"{biz_phone_id}:{recipient_id}"
        
    errors = status.get("errors", [])
    
    return NormalizedEvent(
        message_id=msg_id,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        business_phone_number_id=biz_phone_id,
        business_display_phone_number=biz_display_phone,
        timestamp=timestamp,
        status=status_val,
        direction="outbound", # Status refers to a message we sent
        sender_participant_id=None, # It's a system update about a message
        errors=errors
        # raw_message_json could be status object but field is named raw_message_json
    )
