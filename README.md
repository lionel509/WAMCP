# WhatsApp Ingestion MCP System (WAMCP)

A production-grade system for ingesting WhatsApp webhooks, processing them, and exposing data via Model Context Protocol (MCP) for Claude.

## Features

- **Ingestion**: High-fidelity webhook parsing, idempotency (SHA256), and signature verification.
- **Storage**: normalized Postgres schema (SQLAlchemy + Alembic).
- **Files**: MinIO object storage for media/documents.
- **MCP Server**: Read-only tools (`get_messages`, `search_messages`) with audit logging.
- **Safety**: No automated replies (except explicit Debug Echo mode).

## Setup

1. **Environment**:

   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

2. **Start Services**:

   ```bash
   make dev
   ```

   This starts Postgres, Redis, MinIO, API, Worker, and MCP services.

3. **Migrations**:
   Migrations are run automatically on startup, or manually:

   ```bash
   make db-migrate
   ```

## Testing

- **Unit & Integration**:

  ```bash
  make test
  ```

- **Smoke Test**:

  ```bash
  make smoke
  ```

- **Manual Webhook**:

  ```bash
  ./scripts/send_test_webhook.sh
  ```

## Config

- Canonical WhatsApp/Meta vars: `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WABA_ID`, `WHATSAPP_API_VERSION`, `WHATSAPP_BASE_URL`, `VERIFY_WEBHOOK_SIGNATURE`.
- Debug controls: `DEBUG_ECHO_MODE`, `DEBUG_ECHO_ALLOWLIST_E164`, `DEBUG_ECHO_RATE_LIMIT_SECONDS`, `DEBUG_ECHO_GROUP_FALLBACK` (keep `DEBUG_ECHO_MODE=false` in production).
- Core services: `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `ADMIN_API_KEY`.
- Legacy alias support (canonical wins):
  - `WHATSAPP_ACCESS_TOKEN` ← `WHATSAPP_API_TOKEN`, `WHATSAPP_API_KEY`, `WHATSAPP_TOKEN`
  - `WHATSAPP_VERIFY_TOKEN` ← `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `WHATSAPP_VERIFY`
  - `WHATSAPP_APP_SECRET` ← `WHATSAPP_SECRET`, `APP_SECRET`
  - `VERIFY_WEBHOOK_SIGNATURE` ← `VERIFY_WEBHOOK`, `VERIFY_SIGNATURE`
  - `WHATSAPP_PHONE_NUMBER_ID` ← `PHONE_NUMBER_ID`
  - `WHATSAPP_WABA_ID` ← `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WABA_ID`
  - `MINIO_BUCKET` ← `MINIO_BUCKET_DOCUMENTS`
  Always provide `WHATSAPP_APP_SECRET` when `VERIFY_WEBHOOK_SIGNATURE=true`.

## MCP Configuration (Claude Desktop)

To use this with Claude Desktop:

1. Ensure services are running (`make dev`).
2. Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wamcp": {
      "command": "docker",
      "args": ["exec", "-i", "wamcp-api-1", "python", "-m", "app.mcp.server"]
    }
  }
}
```

*Note: Adjust `wamcp-api-1` if your container name differs.*

## Architecture

- **Api**: FastAPI (Ingestion, Webhooks).
- **Worker**: Celery (Async tasks, Echo, Document processing).
- **Mcp**: FastMCP server.
- **Db**: Postgres 16.

## Admin API

All admin endpoints require the `X-Admin-Api-Key` header matching `ADMIN_API_KEY`.

- `GET /admin/health` — dependency status (Postgres/Redis/MinIO) plus git version.
- `GET /admin/conversations?limit=50&offset=0` — most recently updated conversations.
- `GET /admin/conversations/{conversation_id}/messages?limit=50&before_ts=...` — recent messages for a conversation.
- `GET /admin/search/messages?q=...&conversation_id=...&limit=50` — text search (FTS with ILIKE fallback).
- `GET /admin/documents?conversation_id=...&limit=50` — documents + extraction status.
- `GET /admin/documents/{document_id}` — document metadata and sanitized `extracted_text` (no binaries).

Each admin request is audited (`actor=admin_api`, `action=read`, key parameters only). Example:

```bash
curl -H "X-Admin-Api-Key: $ADMIN_API_KEY" http://localhost:8000/admin/conversations
```

## Document Extraction

- Worker downloads the raw object from MinIO using `storage_key_raw`, enforces `MAX_DOCUMENT_BYTES` (default 10MB), and never logs raw content.
- Text PDFs use `pypdf`; images (`jpg/png/webp`) use `pytesseract` OCR. Invoices populate `extracted_fields_json` when invoice number/date/total can be detected (empty object otherwise).
- Tesseract runtime is installed in the worker image (`docker/Dockerfile.worker`). For local runs, install the `tesseract-ocr` binary and `pip install -r requirements.txt`.

## Security

- **Secrets**: Managed via `.env` (never committed).
- **Verification**: X-Hub-Signature-256 enforced on webhooks.
- **Audit**: All MCP tool access is logged to `audit_log` table.
- **Prod safety**: Keep `DEBUG_ECHO_MODE=false` in production to avoid unintended replies.
