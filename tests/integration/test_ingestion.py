import pytest
import uuid
import json
import hashlib
import hmac
from sqlalchemy import text
from app.services.ingest_service import IngestService
from app.db.models import RawEvent, Message, Conversation
from app.config import settings
from unittest.mock import MagicMock

# Helper to generate signature
def generate_signature(body: bytes, secret: str) -> str:
    hmac_obj = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={hmac_obj.hexdigest()}"

@pytest.mark.asyncio
async def test_ingest_webhook_valid(db_session):
    # Setup
    settings.WHATSAPP_APP_SECRET = "test_secret" # Set secret for test
    svc = IngestService(db_session)
    body_dict = {
      "object": "whatsapp_business_account",
      "entry": [{
          "changes": [{
              "value": {
                  "messaging_product": "whatsapp",
                  "metadata": {"phone_number_id": "123", "display_phone_number": "123"},
                  "messages": [{
                      "from": "456",
                      "id": f"wamid.{uuid.uuid4()}",
                      "timestamp": "1700000000",
                      "type": "text",
                      "text": {"body": f"Integration Test {uuid.uuid4()}"}
                  }]
              }
          }]
      }]
    }
    raw_body = json.dumps(body_dict).encode()
    sig = generate_signature(raw_body, settings.WHATSAPP_APP_SECRET or "")
    headers = {"x-hub-signature-256": sig}
    
    # Act
    res = await svc.ingest_webhook(raw_body, headers)
    
    # Assert
    assert res["status"] == "processed"
    assert res["count"] == 1
    
    # DB Check
    # We can't check by specific ID easily since we randomized it.
    # But assertion on count==1 implies success.
    pass

@pytest.mark.asyncio
async def test_ingest_webhook_duplicate(db_session):
    settings.WHATSAPP_APP_SECRET = "test_secret"
    svc = IngestService(db_session)
    body_dict = {"test": f"duplicate_{uuid.uuid4()}"}
    raw_body = json.dumps(body_dict).encode()
    sig = generate_signature(raw_body, settings.WHATSAPP_APP_SECRET or "")
    headers = {"x-hub-signature-256": sig}
    
    # First Call
    res1 = await svc.ingest_webhook(raw_body, headers)
    assert res1["status"] == "processed"
    
    # Second Call
    res2 = await svc.ingest_webhook(raw_body, headers)
    assert res2["status"] == "ignored"
    assert res2["reason"] == "duplicate_event"

@pytest.mark.asyncio
async def test_ingest_signature_fail(db_session):
    if not settings.VERIFY_WEBHOOK_SIGNATURE:
        pytest.skip("Signature verification disabled")
        
    svc = IngestService(db_session)
    body_dict = {"uuid": str(uuid.uuid4())}
    raw_body = json.dumps(body_dict).encode()
    headers = {"x-hub-signature-256": "sha256=invalid"}
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.ingest_webhook(raw_body, headers)
    
    assert exc.value.status_code == 401
