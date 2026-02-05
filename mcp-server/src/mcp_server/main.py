import logging
from mcp.server.fastmcp import FastMCP
from mcp_server.tools.search_docs import search_knowledge_base
from mcp_server.core.settings import settings
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = logging.getLogger(__name__)

# Initialize with metadata - allow any host for Kubernetes
mcp = FastMCP(
    "MCP Server to expose tools like Search and Retrieval service",
    dependencies=["httpx", "pydantic-settings"],
    host="0.0.0.0",
)

# Register modularized tools
mcp.add_tool(
    search_knowledge_base,
    name="search_docs",
    description="Searches private knowledge base")


async def health(request):
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "healthy"})


def start():
    """Starts the production web server on the correct port."""
    # Create main app with health endpoint and mount MCP SSE app at /mcp
    # Allow all hosts for Kubernetes internal communication
    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=["*"]),
        ]
    )

    # Force uvicorn to use your configured port (8002)
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)

if __name__ == "__main__":
    start()