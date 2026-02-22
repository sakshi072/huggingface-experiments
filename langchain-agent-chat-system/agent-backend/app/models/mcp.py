from pydantic import BaseModel, Field
import os 

class MCPClientConfig(BaseModel):
    """MCP Client configuration"""

    mcp_server_url: str = Field(
        default="http://mcp-server:8002/mcp/sse",
        description="Secure MCP server URL"
    )
    ca_cert_path: str = Field(default="/etc/mcp/client-certs/ca.crt")
    client_cert_path:str = Field(default="/etc/mcp/client-certs/tls.crt")
    client_key_path: str = Field(default="/etc/mcp/client-certs/tls.key")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retires: int = Field(default=3, description="Maxium retry attempts")

    @classmethod
    def from_env(cls) -> "MCPClientConfig":
        """Load config from environment variables"""
        return cls(
            mcp_server_url=os.getenv("MCP_SERVER_URL", "http://mcp-server:8002/mcp/sse"),
            ca_cert_path=os.getenv("MCP_TLS_CA_CERT", "/etc/mcp/client-certs/ca.crt"),
            client_cert_path=os.getenv("MCP_TLS_CLIENT_CERT", "/etc/mcp/client-certs/tls.crt"),
            client_key_path=os.getenv("MCP_TLS_CLIENT_KEY", "/etc/mcp/client-certs/tls.key"),
            timeout=float(os.getenv("MCP_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("MCP_MAX_RETRIES", "3"))
        )