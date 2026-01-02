import asyncio
import logging

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.mcp import tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Create MCP Server with SSE transport
mcp = FastMCP("WhatsAppMCP")


async def _ensure_db():
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await engine.dispose()

@mcp.tool()
async def list_conversations(limit: int = 10, offset: int = 0) -> dict:
    """List recent conversations."""
    return await tools.list_conversations(limit, offset)

@mcp.tool()
async def get_recent_messages(conversation_id: str, limit: int = 20) -> dict:
    """Get recent messages for a conversation."""
    return await tools.get_recent_messages(conversation_id, limit)

@mcp.tool()
async def search_messages(query: str, limit: int = 50, conversation_id: str | None = None) -> dict:
    """Search messages by text content."""
    return await tools.search_messages(query, limit, conversation_id)

@mcp.tool()
async def list_documents(limit: int = 20) -> dict:
    """List processed documents/invoices."""
    return await tools.list_documents(limit)

if __name__ == "__main__":
    if settings.plugin_mode:
        logger.info("Plugin mode enabled for MCP server; ensuring read-only DB connectivity")
        try:
            asyncio.run(_ensure_db())
        except Exception as exc:
            logger.error("MCP server failed to start due to DB connectivity: %s", exc)
            raise SystemExit(1)

    logger.info("Starting MCP server (plugin_mode=%s)", settings.plugin_mode)
    mcp.run()
