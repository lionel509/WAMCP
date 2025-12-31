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

## Security

- **Secrets**: Managed via `.env` (never committed).
- **Verification**: X-Hub-Signature-256 enforced on webhooks.
- **Audit**: All MCP tool access is logged to `audit_log` table.
