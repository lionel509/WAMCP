# WAMCP Quickstart Setup

This guide walks through a minimal local setup for development and smoke testing.

## 1) Prerequisites
- Docker + Docker Compose
- Make
- Python 3.12 (only needed if running parts outside containers)

## 2) Clone and env file
```bash
git clone https://github.com/lionel509/WAMCP.git
cd WAMCP
cp .env.example .env
```
Edit `.env` with your credentials. Key WhatsApp/Meta vars:
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_APP_SECRET`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_WABA_ID`

For local dev you can leave `VERIFY_WEBHOOK_SIGNATURE=true` and supply `WHATSAPP_APP_SECRET`; or set it to `false` for minimal startup (not recommended for prod).

## 3) Start the stack
```bash
make dev
```
This builds and starts Postgres, Redis, MinIO, API, Worker, MCP, and Watchdog. The API listens on `http://localhost:8000`, MCP SSE on `http://localhost:8080`.

## 4) Verify health
```bash
curl http://localhost:8000/health
```
Expected: `{ "status": "ok", "env": "dev" }`.

## 5) Run tests
```bash
make test   # unit + integration
make smoke  # smoke suite
```

## 6) Common tweaks
- To disable webhook signature verification (dev only), set `VERIFY_WEBHOOK_SIGNATURE=false`.
- To exercise debug echo, set `DEBUG_ECHO_MODE=true` and provide `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`.
- MinIO defaults: endpoint `localhost:9000`, bucket `documents`, creds `minioadmin/minioadmin` (from `.env.example`).

## 7) Stopping services
```bash
make down
```

## 8) Troubleshooting
- If containers fail to import the `app` package, ensure `app/__init__.py` exists (it is present in repo) and rebuild: `docker compose up --build`.
- If MCP is not reachable on 8080, check container logs: `docker compose logs mcp`.
- For DB issues, reset local volumes: `docker compose down -v` (destroys data).
