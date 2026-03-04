import asyncio
import logging
import time
from typing import Optional, List, Callable
from contextlib import AsyncExitStack
from langchain_mcp_adapters.client import MultiServerMCPClient
from app.models.mcp import MCPClientConfig
from app.infrastructure.auth.token_manager import get_access_token

logger = logging.getLogger(__name__)


class MCPClientSSL:
    def __init__(self, config: Optional[MCPClientConfig] = None):
        self.config = config or MCPClientConfig.from_env()
        self._tools_cached: List = []
        self._last_refresh_time: float = 0
        self._ttl: int = 300
        self._lock = asyncio.Lock()
        logger.info(f"MCP Client initialized for {self.config.mcp_server_url}")

    async def _server_config(self) -> dict:
        token = await get_access_token('RETRIEVAL_MCP')
        return {
            "knowledge": {
                "url": self.config.mcp_server_url,
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }

    async def discover_tools(self) -> List:
        """Raw tool definitions for ToolRegistry cache — no LangChain conversion"""
        current_time = time.monotonic()

        if self._tools_cached and (current_time - self._last_refresh_time < self._ttl):
            logger.info(f"Returning {len(self._tools_cached)} cached tools")
            return self._tools_cached

        async with self._lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if self._tools_cached and (time.monotonic() - self._last_refresh_time < self._ttl):
                return self._tools_cached

            logger.info("Cache expired or empty. Fetching fresh tools...")
            for attempt in range(self.config.max_retires):
                try:
                    client = MultiServerMCPClient(self._server_config())
                    tools = await client.get_tools()  # no async with
                    self._tools_cached = tools
                    self._last_refresh_time = time.monotonic()
                    logger.info(f"Cache updated with {len(tools)} tools")
                    return self._tools_cached
                except Exception as e:
                    logger.warning(f"Failed to fetch tools (attempt {attempt+1}): {e}")
                    if attempt < self.config.max_retires - 1:
                        await asyncio.sleep(2 ** attempt)
                    elif not self._tools_cached:
                        raise

        return self._tools_cached

    def _wrap_with_status(self, tools: List, on_status: Callable) -> List:
        """Inject status notifications around tool execution"""
        for tool in tools:
            original = tool.coroutine
            tool_name = tool.name

            def make_wrapper(orig, name):
                async def wrapped(**kwargs):
                    await on_status(f"Searching knowledge base...")
                    try:
                        result = await orig(**kwargs)
                        await on_status("Finished")
                        return result
                    except Exception as e:
                        await on_status(f"Tool {name} failed")
                        raise
                return wrapped

            tool.coroutine = make_wrapper(original, tool_name)
        return tools


# Global instance
_mcp_client: Optional[MCPClientSSL] = None

def get_mcp_client(config: Optional[MCPClientConfig] = None) -> MCPClientSSL:
    global _mcp_client
    if not _mcp_client:
        _mcp_client = MCPClientSSL(config)
    return _mcp_client

async def get_mcp_tools() -> List:
    """Keep for backwards compatibility / ToolRegistry"""
    client = get_mcp_client()
    return await client.discover_tools()