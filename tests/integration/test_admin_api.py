import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.db.models import (
    AuditLog,
    Conversation,
    ConversationType,
    DocType,
    Document,
    ExtractionStatus,
    Message,
    MessageDirection,
    Participant,
)
from app.main import app
from app.services.ingest_service import IngestService


@pytest.mark.asyncio
async def test_admin_endpoints_return_seeded_rows(db_session):
    convo = Conversation(
        id="biz1:user1",
        type=ConversationType.INDIVIDUAL,
        business_phone_number_id="biz1",
        display_name="Test User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    participant = Participant(id="user1", phone_e164="user1")
    message = Message(
        id="msg-admin-1",
        conversation_id=convo.id,
        participant_id=participant.id,
        direction=MessageDirection.INBOUND,
        sent_at=datetime.now(timezone.utc),
        message_type="text",
        text_body="admin searchable text",
    )
    document = Document(
        id=uuid.uuid4(),
        message_id=message.id,
        doc_type=DocType.PDF,
        mime_type="application/pdf",
        storage_key_raw="test/key",
        extracted_text="document text body",
        extraction_status=ExtractionStatus.OK,
    )

    db_session.add_all([convo, participant, message, document])
    await db_session.commit()

    headers = {"X-Admin-Api-Key": settings.admin_api_key}
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/admin/conversations", headers=headers)
        assert resp.status_code == 200
        convo_ids = [c["id"] for c in resp.json()["conversations"]]
        assert convo.id in convo_ids

        resp = await client.get(f"/admin/conversations/{convo.id}/messages", headers=headers)
        assert resp.status_code == 200
        msg_ids = [m["id"] for m in resp.json()["messages"]]
        assert message.id in msg_ids

        resp = await client.get(
            "/admin/search/messages",
            headers=headers,
            params={"q": "searchable", "conversation_id": convo.id},
        )
        assert resp.status_code == 200
        assert any(m["id"] == message.id for m in resp.json()["messages"])

        resp = await client.get("/admin/documents", headers=headers, params={"conversation_id": convo.id})
        assert resp.status_code == 200
        assert any(d["id"] == str(document.id) for d in resp.json()["documents"])

        resp = await client.get(f"/admin/documents/{document.id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["extracted_text"] == "document text body"

    audit_count = await db_session.execute(
        select(func.count(AuditLog.id)).where(AuditLog.actor == "admin_api")
    )
    assert audit_count.scalar() >= 5


@pytest.mark.asyncio
async def test_admin_endpoints_after_ingest(db_session):
    original_verify_primary = settings.VERIFY_WEBHOOK_SIGNATURE_PRIMARY
    settings.VERIFY_WEBHOOK_SIGNATURE_PRIMARY = False

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "abc", "display_phone_number": "12345"},
                            "messages": [
                                {
                                    "from": "55501",
                                    "id": "wamid.integration",
                                    "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                                    "type": "text",
                                    "text": {"body": "hello from webhook"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }

    try:
        ingest = IngestService(db_session)
        await ingest.ingest_webhook(json.dumps(payload).encode(), headers={})

        headers = {"X-Admin-Api-Key": settings.admin_api_key}
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.get("/admin/conversations", headers=headers)
            assert resp.status_code == 200
            conversations = resp.json()["conversations"]
            assert conversations
            conv_id = conversations[0]["id"]

            resp = await client.get(f"/admin/conversations/{conv_id}/messages", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["messages"]
    finally:
        settings.VERIFY_WEBHOOK_SIGNATURE_PRIMARY = original_verify_primary
