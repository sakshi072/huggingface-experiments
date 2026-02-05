from pydantic import BaseModel, Field
import os 

class MCPClientConfig(BaseModel):
    """MCP Client configuration"""

    mcp_server_url: str = Field(
        default="http://mcp-server:8002/mcp/sse",
        description="MCP server SSE endpoint URL"
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retires: int = Field(default=3, description="Maxium retry attempts")

    @classmethod
    def from_env(cls) -> "MCPClientConfig":
        """Load config from environment variables"""
        return cls(
            mcp_server_url=os.getenv("MCP_SERVER_URL", "http://localhost:8002/mcp/sse"),
            timeout=float(os.getenv("MCP_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("MCP_MAX_RETRIES", "3"))
        )