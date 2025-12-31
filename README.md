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

2. **Start Services** (local development):

   ```bash
   make dev
   ```

   This starts Postgres, Redis, MinIO, API, Worker, and MCP services.

3. **Start with Cloudflare Tunnel** (if exposing webhooks to Meta):

   ```bash
   make dev-tunnel
   ```

   See [Cloudflare Tunnel Setup](#cloudflare-tunnel-setup) below.

4. **Migrations**:
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

## Sending & Receiving WhatsApp Messages

### Receiving Messages (Webhooks from Meta)

Your app automatically receives and stores all incoming WhatsApp messages via the webhook endpoint.

**Setup:**
1. Start the tunnel: `make tunnel`
2. Get your public URL: `make tunnel-url`
3. Set `PUBLIC_BASE_URL` in `.env` to your tunnel URL (optional, API logs this on startup)
4. Configure Meta webhook callback:
   - **Callback URL**: `https://<your-url>/webhooks/whatsapp`
   - **Verify Token**: Must match `WHATSAPP_VERIFY_TOKEN` from `.env` (default: `dev-verify-token`)

**Test the webhook:**
```bash
curl -X GET "https://<your-tunnel-url>/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=dev-verify-token&hub.challenge=test_challenge"
```

When Meta sends a webhook, your API:
- Verifies the signature using `WHATSAPP_APP_SECRET`
- Stores the raw event in the database
- Parses and normalizes the message
- Stores conversations, participants, and messages
- Optional: Triggers debug echo (auto-reply) if enabled

**View received messages:**
```bash
curl -H "X-Admin-Api-Key: admin123" http://localhost:8000/admin/conversations
curl -H "X-Admin-Api-Key: admin123" http://localhost:8000/admin/conversations/{id}/messages
```

**Troubleshooting:**
- **Not receiving messages?** Check that:
  1. Meta webhook callback URL is set correctly in [App Dashboard > WhatsApp > Configuration](https://developers.facebook.com/apps)
  2. Verify Token matches `WHATSAPP_VERIFY_TOKEN` in your `.env`
  3. If using a tunnel: `PUBLIC_BASE_URL` in `.env` matches your tunnel URL
  4. API logs show `Webhook Callback URL for Meta: ...` on startup
  5. Enable `DEBUG_ECHO_MODE=true` to auto-reply and test end-to-end

### Sending Messages

Your app can send three types of WhatsApp messages:

#### 1. **Text Messages**

**Via API:**
```bash
curl -X POST http://localhost:8000/send/text \
  -H "X-Admin-Api-Key: admin123" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "15169007810",
    "body": "Hello from WAMCP!",
    "preview_url": false
  }'
```

**Via Script:**
```bash
./scripts/send_whatsapp_message.sh 15169007810 (will eventually call the API)
```

#### 2. **Template Messages**

Pre-approved message templates from Meta (e.g., `hello_world`).

**Via API:**
```bash
curl -X POST http://localhost:8000/send/template \
  -H "X-Admin-Api-Key: admin123" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "15169007810",
    "template_name": "hello_world",
    "language_code": "en_US",
    "parameters": ["John"]
  }'
```

#### 3. **Media Messages**

Send images, documents, audio, or video.

**Via API:**
```bash
curl -X POST http://localhost:8000/send/media \
  -H "X-Admin-Api-Key: admin123" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "15169007810",
    "media_type": "image",
    "media_url": "https://example.com/image.jpg",
    "caption": "Check this out!"
  }'
```

### Debug Echo Mode

Auto-reply to incoming messages when `DEBUG_ECHO_MODE=true`.

**Configuration:**
```env
DEBUG_ECHO_MODE=true
DEBUG_ECHO_ALLOWLIST_E164=5169007810  # Only echo replies from this number
DEBUG_ECHO_RATE_LIMIT_SECONDS=60      # Don't echo same person more than once per 60s
DEBUG_ECHO_GROUP_FALLBACK=false       # Don't auto-reply in groups
```

When enabled:
- User sends: "Hello"
- Bot replies: "Received: Hello"

⚠️ **Keep `DEBUG_ECHO_MODE=false` in production** to avoid unintended replies.

## Config

- **Public URL** (optional): `PUBLIC_BASE_URL` - Set when using a reverse proxy, tunnel, or production domain. Used for webhook callback URLs and external links. API logs this on startup.
- **Canonical WhatsApp/Meta vars**: `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WABA_ID`, `WHATSAPP_API_VERSION`, `WHATSAPP_BASE_URL`, `VERIFY_WEBHOOK_SIGNATURE`.
- **Debug controls**: `DEBUG_ECHO_MODE`, `DEBUG_ECHO_ALLOWLIST_E164`, `DEBUG_ECHO_RATE_LIMIT_SECONDS`, `DEBUG_ECHO_GROUP_FALLBACK` (keep `DEBUG_ECHO_MODE=false` in production).
- **Core services**: `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `ADMIN_API_KEY`.
- **Legacy alias support** (canonical wins):
  - `WHATSAPP_ACCESS_TOKEN` ← `WHATSAPP_API_TOKEN`, `WHATSAPP_API_KEY`, `WHATSAPP_TOKEN`
  - `WHATSAPP_VERIFY_TOKEN` ← `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `WHATSAPP_VERIFY`
  - `WHATSAPP_APP_SECRET` ← `WHATSAPP_SECRET`, `APP_SECRET`
  - `VERIFY_WEBHOOK_SIGNATURE` ← `VERIFY_WEBHOOK`, `VERIFY_SIGNATURE`
  - `WHATSAPP_PHONE_NUMBER_ID` ← `PHONE_NUMBER_ID`
  - `WHATSAPP_WABA_ID` ← `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WABA_ID`
  - `MINIO_BUCKET` ← `MINIO_BUCKET_DOCUMENTS`
  
**Important:**
  - Always provide `WHATSAPP_APP_SECRET` when `VERIFY_WEBHOOK_SIGNATURE=true`.
  - For tunnels/proxies: Set `PUBLIC_BASE_URL` to match your tunnel URL (e.g., `https://my-tunnel.cloudflare.com`) and use it in Meta's webhook callback URL.

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

## Cloudflare Tunnel Setup

To expose your local stack to Meta WhatsApp webhooks during development, use **Quick Tunnel** (auto-generates a public URL instantly—no token needed).

### Quick Tunnel (Recommended for Local Dev)

Perfect for testing Meta webhooks on your local machine.

**Step 1: Start the tunnel**
```bash
make tunnel
```

This starts your entire stack including a Cloudflare tunnel that exposes your API to the internet.

**Step 2: Find your public URL**
```bash
make tunnel-url
```

This prints your temporary public URL (e.g., `https://abc123-def456.trycloudflare.com`). It changes every time you restart.

**Step 3: Configure Meta Webhook**
1. Go to **Meta App Dashboard** → **WhatsApp** → **Configuration**
2. Set **Callback URL**: `https://<your-public-url>/webhooks/whatsapp`
3. Set **Verify Token**: Must match `WHATSAPP_VERIFY_TOKEN` from `.env`
4. Click **Verify and Save**

**Step 4: Test it**
```bash
# Monitor logs
make tunnel-logs

# In another terminal, test the webhook
curl -X GET "https://<your-public-url>/webhooks/whatsapp?hub.challenge=test"
```

### Persistent Tunnel (Using Token)

If you need a stable hostname that persists across restarts, follow the instructions in [infra/cloudflared/README.md](infra/cloudflared/README.md).

### Useful Commands

```bash
# Start stack with tunnel
make tunnel

# View tunnel connection status
make tunnel-logs

# Extract the public URL (best-effort)
make tunnel-url

# Stop everything
make down
```

⚠️ **Important Notes:**
- Quick tunnels generate a new random URL on each restart
- Never use quick tunnel or expose credentials in production
- The tunnel only exposes the API; Postgres, Redis, MinIO remain internal

## Document Extraction

- Worker downloads the raw object from MinIO using `storage_key_raw`, enforces `MAX_DOCUMENT_BYTES` (default 10MB), and never logs raw content.
- Text PDFs use `pypdf`; images (`jpg/png/webp`) use `pytesseract` OCR. Invoices populate `extracted_fields_json` when invoice number/date/total can be detected (empty object otherwise).
- Tesseract runtime is installed in the worker image (`docker/Dockerfile.worker`). For local runs, install the `tesseract-ocr` binary and `pip install -r requirements.txt`.

## Security

- **Secrets**: Managed via `.env` (never committed).
- **Verification**: X-Hub-Signature-256 enforced on webhooks.
- **Audit**: All MCP tool access is logged to `audit_log` table.
- **Prod safety**: Keep `DEBUG_ECHO_MODE=false` in production to avoid unintended replies.
