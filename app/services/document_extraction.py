import asyncio
import hashlib
import io
import logging
import re
from typing import Dict, Optional, Tuple

import httpx
import pytesseract
from PIL import Image
from pypdf import PdfReader

from app.config import settings
from app.db.models import DocType, Document
from app.integrations.minio_client import minio_client

logger = logging.getLogger(__name__)


class DocumentExtractionError(Exception):
    """Base exception for document extraction failures."""


class DocumentTooLargeError(DocumentExtractionError):
    """Raised when a document exceeds the configured size limit."""


class DocumentNotFoundError(DocumentExtractionError):
    """Raised when a document cannot be located in storage."""


def sanitize_text(text: Optional[str]) -> str:
    """
    Remove control characters and collapse excessive whitespace.
    Keeps newlines so the caller can preserve layout where possible.
    """
    if not text:
        return ""

    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    # Normalize multiple blank lines to a single newline
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_invoice_fields(text: str) -> Dict[str, Optional[str]]:
    """
    Attempt to pull simple invoice fields from extracted free text.
    Returns keys only when detected; callers may persist an empty dict.
    """
    fields: Dict[str, Optional[str]] = {}
    invoice_match = re.search(r"invoice(?:\s*(number|no\.|#))?\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if invoice_match:
        fields["invoice_number"] = invoice_match.group(2)

    date_match = re.search(
        r"(?:invoice\s*)?date\s*[:\-]?\s*((?:\d{4}-\d{2}-\d{2})|(?:\d{2}/\d{2}/\d{4}))",
        text,
        re.IGNORECASE,
    )
    if date_match:
        fields["date"] = date_match.group(1)

    total_match = re.search(
        r"(?:total|amount due|balance due)\s*[:\-]?\s*\$?\s*([0-9]{1,3}(?:[,0-9]{0,3})*(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if total_match:
        fields["total"] = total_match.group(1)

    return fields


def _extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    texts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        texts.append(page_text)
    return "\n".join(texts)


def _extract_image_text(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img)


class DocumentExtractionService:
    def __init__(self, storage_client=minio_client):
        self.storage_client = storage_client

    async def process(
        self,
        document: Document,
        media_url: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> Tuple[str, Optional[Dict[str, Optional[str]]]]:
        """
        Fetch the document bytes (from MinIO or media_url), enforce limits, extract text,
        and return sanitized text plus optional structured fields.
        """
        raw_bytes = await self._load_document_bytes(document, media_url, headers)

        if len(raw_bytes) > settings.MAX_DOCUMENT_BYTES:
            raise DocumentTooLargeError(
                f"Document size {len(raw_bytes)} exceeds limit {settings.MAX_DOCUMENT_BYTES}"
            )

        text = await asyncio.to_thread(self._extract_text_for_document, document, raw_bytes)
        sanitized = sanitize_text(text)

        fields = None
        if document.doc_type == DocType.INVOICE:
            fields = extract_invoice_fields(sanitized)
            if fields is None:
                fields = {}

        return sanitized, fields

    async def _load_document_bytes(
        self, document: Document, media_url: Optional[str], headers: Optional[dict]
    ) -> bytes:
        if document.storage_key_raw:
            data = await asyncio.to_thread(self.storage_client.download_data, document.storage_key_raw)
            if data is None:
                raise DocumentNotFoundError("Document not found in object storage")
            return data

        if media_url:
            data = await self._download_media(media_url, headers)
            key = f"{document.id}/raw"
            stored = await asyncio.to_thread(
                self.storage_client.upload_data, key, data, document.mime_type or "application/octet-stream"
            )
            if not stored:
                raise DocumentExtractionError("Failed to persist document to storage")
            document.storage_key_raw = key
            document.sha256 = hashlib.sha256(data).hexdigest()
            return data

        raise DocumentNotFoundError("No storage key available for document")

    async def _download_media(self, url: str, headers: Optional[dict]) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers or {}, timeout=30.0)
            resp.raise_for_status()
            return resp.content

    def _extract_text_for_document(self, document: Document, data: bytes) -> str:
        mime = (document.mime_type or "").lower()
        is_pdf = document.doc_type == DocType.PDF or mime.startswith("application/pdf") or data.startswith(b"%PDF")
        is_image = document.doc_type == DocType.IMAGE or mime.startswith("image/")

        if document.doc_type == DocType.INVOICE:
            # Determine if invoice is pdf or image based on mime/header
            if mime.startswith("image/"):
                is_image = True
                is_pdf = False
            elif mime.startswith("application/pdf") or data.startswith(b"%PDF"):
                is_pdf = True
                is_image = False

        if is_pdf:
            return _extract_pdf_text(data)
        if is_image:
            return _extract_image_text(data)

        raise DocumentExtractionError(f"Unsupported document type {document.doc_type} with mime {document.mime_type}")
