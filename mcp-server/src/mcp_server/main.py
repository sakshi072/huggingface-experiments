import logging
from mcp.server.fastmcp import FastMCP
from mcp_server.tools.search_docs import search_knowledge_base
from mcp_server.core.settings import settings
import uvicorn

logger = logging.getLogger(__name__)

# Initialize with metadata
mcp = FastMCP(
    "MCP Server to expose tools like Search and Retrieval service",
    dependencies=["httpx", "pydantic-settings"]
)

# Register modularized tools
mcp.add_tool(
    search_knowledge_base,
    name="search_docs",
    description="Searches private knowledge base")

def start():
    """Starts the production web server on the correct port."""
    # Use sse_app() instead of get_sse_app()
    app = mcp.sse_app() 
    
    # Force uvicorn to use your configured port (8002)
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)

if __name__ == "__main__":
    start()