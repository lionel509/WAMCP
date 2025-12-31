from mcp.server.fastmcp import FastMCP
from app.mcp import tools
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Create MCP Server
mcp = FastMCP("WhatsAppMCP")

@mcp.tool()
async def list_conversations(limit: int = 10, offset: int = 0) -> dict:
    """List recent conversations."""
    return await tools.list_conversations(limit, offset)

@mcp.tool()
async def get_recent_messages(conversation_id: str, limit: int = 20) -> dict:
    """Get recent messages for a conversation."""
    return await tools.get_recent_messages(conversation_id, limit)

@mcp.tool()
async def search_messages(query: str, limit: int = 50, conversation_id: str = None) -> dict:
    """Search messages by text content."""
    return await tools.search_messages(query, limit, conversation_id)

@mcp.tool()
async def list_documents(limit: int = 20) -> dict:
    """List processed documents/invoices."""
    return await tools.list_documents(limit)

if __name__ == "__main__":
    # Run the server
    # FastMCP by default runs SSE on port 8000? Or depends on `run()`.
    # We want to expose it on port 8080 (as per docker-compose).
    mcp.run(host="0.0.0.0", port=8080)
