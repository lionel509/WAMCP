import uuid
from pathlib import Path

import pytest

from app.db.models import DocType, Document, ExtractionStatus
from app.workers.tasks import _process_document_async


class InMemoryStorage:
    def __init__(self):
        self.data: dict[str, bytes] = {}

    def download_data(self, key: str) -> bytes | None:
        return self.data.get(key)

    def upload_data(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        self.data[key] = data
        return True


@pytest.mark.asyncio
async def test_process_document_populates_text(db_session):
    storage = InMemoryStorage()
    key = "integration/doc"
    storage.data[key] = Path("tests/fixtures/docs/sample_text.pdf").read_bytes()

    doc = Document(
        id=uuid.uuid4(),
        message_id="msg-int-1",
        doc_type=DocType.PDF,
        mime_type="application/pdf",
        storage_key_raw=key,
        extraction_status=ExtractionStatus.PENDING,
    )
    db_session.add(doc)
    await db_session.commit()

    await _process_document_async(str(doc.id), storage_client=storage)

    refreshed = await db_session.get(Document, doc.id)
    assert refreshed is not None
    assert refreshed.extraction_status == ExtractionStatus.OK
    assert refreshed.extraction_error is None
    assert "sample PDF document" in (refreshed.extracted_text or "")
