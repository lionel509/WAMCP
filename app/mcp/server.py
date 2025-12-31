from mcp.server.fastmcp import FastMCP
from app.mcp import tools
import logging
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Create MCP Server with SSE transport
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
    # Run the MCP server
    # FastMCP.run() starts the server (stdio transport by default)
    mcp.run()
