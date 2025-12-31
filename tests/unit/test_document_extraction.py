import uuid
from pathlib import Path

import pytest

from app.db.models import DocType, Document
from app.services.document_extraction import (
    DocumentExtractionService,
    DocumentTooLargeError,
    extract_invoice_fields,
    sanitize_text,
)
from app.config import settings


FIXTURES = Path("tests/fixtures/docs")


class FakeStorage:
    def __init__(self):
        self.data: dict[str, bytes] = {}

    def download_data(self, key: str) -> bytes | None:
        return self.data.get(key)

    def upload_data(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        self.data[key] = data
        return True


def load_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_sanitize_text_collapses_control_chars():
    raw = "Hello\x00World\nNext"
    assert sanitize_text(raw) == "HelloWorld\nNext"


def test_extract_invoice_fields_parses_core_values():
    text = "Invoice Number: INV-42 Date: 2024-10-01 Total: $99.50"
    fields = extract_invoice_fields(text)
    assert fields["invoice_number"] == "INV-42"
    assert fields["date"] == "2024-10-01"
    assert fields["total"] == "99.50"


@pytest.mark.asyncio
async def test_pdf_extraction_via_service():
    storage = FakeStorage()
    key = "doc/raw"
    storage.data[key] = load_bytes("sample_text.pdf")
    doc = Document(
        id=uuid.uuid4(),
        message_id="msg-1",
        doc_type=DocType.PDF,
        mime_type="application/pdf",
        storage_key_raw=key,
    )

    service = DocumentExtractionService(storage)
    text, fields = await service.process(doc)

    assert "sample PDF document" in text
    assert fields is None


@pytest.mark.asyncio
async def test_image_ocr_extraction_via_service():
    storage = FakeStorage()
    key = "img/raw"
    storage.data[key] = load_bytes("sample_image.png")
    doc = Document(
        id=uuid.uuid4(),
        message_id="msg-2",
        doc_type=DocType.IMAGE,
        mime_type="image/png",
        storage_key_raw=key,
    )

    service = DocumentExtractionService(storage)
    text, _ = await service.process(doc)

    assert "OCR" in text.upper()
    assert "TEST" in text.upper()


@pytest.mark.asyncio
async def test_invoice_extraction_includes_fields():
    storage = FakeStorage()
    key = "invoice/raw"
    storage.data[key] = load_bytes("sample_invoice.pdf")
    doc = Document(
        id=uuid.uuid4(),
        message_id="msg-3",
        doc_type=DocType.INVOICE,
        mime_type="application/pdf",
        storage_key_raw=key,
    )

    service = DocumentExtractionService(storage)
    text, fields = await service.process(doc)

    assert "INV-1001" in text
    assert fields is not None
    assert fields.get("invoice_number") == "INV-1001"
    assert fields.get("date") == "2024-01-15"
    assert fields.get("total") == "123.45"


@pytest.mark.asyncio
async def test_size_limit_enforced():
    storage = FakeStorage()
    key = "big/raw"
    storage.data[key] = b"0" * (settings.MAX_DOCUMENT_BYTES + 1)
    doc = Document(
        id=uuid.uuid4(),
        message_id="msg-4",
        doc_type=DocType.PDF,
        mime_type="application/pdf",
        storage_key_raw=key,
    )

    service = DocumentExtractionService(storage)
    with pytest.raises(DocumentTooLargeError):
        await service.process(doc)
