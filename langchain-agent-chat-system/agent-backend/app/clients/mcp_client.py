from fastmcp import Client
from langchain_core.tools import StructuredTool
import logging
from app.models.mcp import MCPClientConfig
from typing import Optional, Dict, List, Any
import asyncio
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

class MCPClient:
    """
    MCP client using fastmcp.client
    
    Features - 
    - Uses FastMCP SDK
    - Automatic connection management
    - Built-in retry and error handling
    - Type-safe tool execution
    - Connection pooling handled by fastmcp
    """

    def __init__(self, config: Optional[MCPClientConfig]= None):
        """Initialize MCP Clinet"""
        self.config = config or MCPClientConfig.from_env()

        self._client = Client(self.config.mcp_server_url)
        self._tools_cache: Dict[str, StructuredTool] = {}

        logger.info(f"MCP client initialized: {self.config.mcp_server_url}")

    
    async def discover_tools(self) -> List[StructuredTool]:
        """ Get list of all tools from mcp server and convert them to langchain tools"""

        logger.info("Getting list of all available tools from MCP server ")

        try:
            async with self._client as client:
                tools_response = await client.list_tools()

                logger.info(f"Raw tools_response: {tools_response}")
                logger.info(f"tools_response type: {type(tools_response)}")

                # Handle both list and object with .tools attribute
                if isinstance(tools_response, list):
                    mcp_tools = tools_response
                elif hasattr(tools_response, 'tools'):
                    mcp_tools = tools_response.tools
                else:
                    logger.info("No tools found from this mcp server")
                    return []

                if not mcp_tools:
                    logger.info("No tools found from this mcp server")
                    return []

                logger.info(f"Found {len(mcp_tools)} MCP tools")

                langchain_tools = []

                # Convert each MCP tool to langchain tool
                for mcp_tool in mcp_tools:
                    try:
                        langchain_tool = self._convert_to_langchain_tool(mcp_tool, client)
                        langchain_tools.append(langchain_tool)

                        self._tools_cache[mcp_tool.name] = langchain_tool
                        logger.info(f"Registered: {mcp_tool.name}")
                    
                    except Exception as e:
                        logger.waring(f"Failed to register {mcp_tool.name}: {e}")
                        continue
                
                logger.info(f"Discovered {len(langchain_tools)} tools from MCP server")
                return langchain_tools
        except Exception as e:
            logger.error(f"Tool discovery failed: {e}")

            if self._tools_cache:
                logger.warning(f"Using {len(self._tools_cache)} cached tools")
                return list(self._tools_cache.values())
            
            raise
    
    def _convert_to_langchain_tool(
        self,
        mcp_tool:Any,
        client: Client
    ) -> StructuredTool:
        """
        Convert mcp tool to Langchain Structured tool
        """
        # Extract tool metadata
        tool_name = mcp_tool.name
        tool_description = mcp_tool.description or f"Execute {tool_name}"

        # Build pydantic model from MCP schema
        # input_schema = self._build_pydantic_model(mcp_tool)

        # Create async execution function that uses fastmcp client
        async def execute_tool(**kwargs) -> str:
            """Execute tool vis FastMCP client"""
            return await self._call_too_with_client(tool_name, kwargs)
        
        # Create langchain tool
        return StructuredTool(
            name=tool_name,
            description=tool_description,
            func=execute_tool,
            coroutine=execute_tool,
            args_schema=mcp_tool.inputSchema
        )

    def _build_pydantic_model(
        self,
        mcp_tool:Any
    ) -> type[BaseModel]:
        """Build pydantic model from mcp tool schema"""
        
        schema = mcp_tool.inputSchema

        properties = schema.get('properties', [])
        required = schema.get('required', [])

        # Build field definitions
        fields = {}
        for field_name, field_def in properties.items():
            field_type = self._map_json_type_to_python(field_def.get('type', 'string'))
            field_descriptipn = field_def.get('description', '')

            # Check if requried
            is_required = field_name in required

            if is_required:
                fields[field_name] = (
                    field_type,
                    Field(description=field_descriptipn)
                )
            else:
                fields[field_name] = (
                    Optional[field_type],
                    Field(default=None, description=field_descriptipn)
                )
        # create dynamic pydantic model
        model = create_model(
            f"{mcp_tool.name}_input",
            **fields
        )

        return model
    
    def _map_json_type_to_python(self, json_type:str) -> type:
        """Map JSON schema types to Python types"""
        type_map = {
            "string":str,
            "integer":int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }

        return type_map.get(json_type, str)

    async def _call_too_with_client(
        self,
        tool_name:str,
        arguments: Dict[str, Any]
    ) -> str:
        """Call MCP tool using FastMCP Client with retry logic"""

        for attempt in range(self.config.max_retires):
            try:
                logger.debug(f"Calling {tool_name} (attempt {attempt+1})")

                async with self._client as client:
                    # FastMCP expects arguments wrapped in "args"
                    # wrapped_args = {"args": arguments}
                    result = await client.call_tool(tool_name, arguments)

                    if hasattr(result, 'content') and result.content:
                        first_content = result.content[0]

                        if hasattr(first_content, 'text'):
                            return first_content.text
                        elif hasattr(first_content, 'data'):
                            return first_content.data
                        
                    return str(result)
                
            except Exception as e:
                logger.warning(f"Tool call failed (attempt {attempt+1}): {e}")

                if attempt < self.config.max_retires -1:
                    await asyncio.sleep(2**attempt)
                    continue
                else:
                    error_msg = f"Tool {tool_name} failed after {self.config.max_retires} attempts: {e}"
                    logger.error(f"{error_msg}")
                    return f"Error: {error_msg}"
    
    async def health_check(self) -> bool:
        """Check MCP server health"""
        try:
            async with self._client as client:
                response = await client.list_tools()
                logger.debug(f"MCP health check: healthy, tools: {response}")
                return True

        except Exception as e:
            logger.warning(f"MCP health check failed: {e}")
            return False
    
    def get_cached_tools(self) -> List[StructuredTool]:
        """Return cached tools without server call"""
        return list(self._tools_cache.values())
    
# Global instance (singleton)
_mcp_client: Optional[MCPClient] = None

def get_mcp_client(config: Optional[MCPClientConfig] = None) -> MCPClient:
    """return MCP client"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient(config)
    return _mcp_client

async def get_mcp_tools() -> List[StructuredTool]:
    """Convenience function to get all MCP tools"""
    client = get_mcp_client()
    return await client.discover_tools()