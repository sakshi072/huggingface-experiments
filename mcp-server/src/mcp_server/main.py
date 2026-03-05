import logging
# from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP
from mcp_server.tools.search_docs import search_knowledge_base
from mcp_server.core.settings import settings
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastmcp.server.auth.providers.jwt import JWTVerifier
from src.mcp_server.core.settings import settings

logger = logging.getLogger(__name__)

# Auth0 M2M - FastMCP validates incoming Bearer tokens automatically
auth = JWTVerifier(
    jwks_uri=settings.auth0_langchain_jwks_url,
    issuer=settings.auth0_langchain_issuer,
    audience=settings.AUTH0_LANGCHAIN_CLIENT_AUDIENCE,
    algorithm="RS256"
)

# Initialize with metadata - allow any host for Kubernetes
mcp = FastMCP(
    "MCP Server to expose tools like Search and Retrieval service",
    auth=auth
)

# Register modularized tools
mcp.tool(search_knowledge_base)

@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "healthy"})

app = mcp.http_app()

def start():
    """Starts the production web server on the correct port."""
    logger.info(f"Starting Local MCP Server with mTLS on port {settings.PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info"
    )

if __name__ == "__main__":
    start()