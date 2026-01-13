"""
RAG Client with OAuth 2.0 Client Credentials authentication
"""
import httpx
import logging
from typing import Optional, List, Dict

from .auth0_token_manager import get_access_token

logger = logging.getLogger(__name__)

class RAGClient:
    """RAG Client"""

    def __init__(self, rag_url: str = "http://localhost:8001"):
        self.rag_url = rag_url.rstrip('/')
        logger.info(f"RAG CLient initialized: {self.rag_url}")

    async def _get_headers(self) -> dict:
        """
        Build request headers with OAuth access token
        
        Returns:
            Headers with Authorization: Bearer <token>
        """
        access_token = await get_access_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

    async def search(self, query:str, top_k:int=3) -> Optional[List[Dict]]:
        """
        Search RAG knowledge base
        
        Args:
            query: User question
            top_k: Number of results
            
        Returns:
            List of source chunks or None if error
        """
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.rag_url}/search",
                    json={"query":query, "top_k":top_k},
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"RAG returned {len(data.get('sources', []))} sources")
                    return data.get('sources', [])
                elif response.status_code == 401:
                    logger.error("RAG authentication failed: Token invalid or expired")
                    return None
                elif response.status_code == 403:
                    logger.error("RAG authorization failed: Insufficient permissions/scopes")
                    return None
                else:
                    logger.warning(f"RAG search failed: {response.status_code}")
                    return None
        except httpx.TimeoutException:
            logger.error("RAG request timeout")
            return None
        except Exception as e:
            logger.error(f"RAG error: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if RAG service is available"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.rag_url}/health")
                return response.status_code == 200
        except:
            return False

# Global instance
_rag_client = None

def get_rag_client() -> RAGClient:
    """Get global RAG client"""
    global _rag_client
    if _rag_client is None:
        _rag_client = RAGClient()
    return _rag_client

def get_rag_tool_definition() -> dict:
    """
    OpenAI/HuggingFace function calling format
    
    This tells the LLM:
    - What the tool does
    - When to use it
    - What parameters it needs
    """
    return {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the knowledge base for factual information, documentation, "
                "or specific details. Use this when:\n"
                "- User asks factual questions\n"
                "- You need to verify information\n"
                "- User requests sources or references\n"
                "- Question is about specific topics in the knowledge base\n"
                "Do NOT use for: greetings, opinions, creative tasks, or general conversation."
            ),
            "parameters":{
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query":{
                        "type": "string",
                        "description": (
                            "Search query - extract the core question or topic. "
                            "Examples: 'machine learning definition', 'neural networks how they work'"
                        )
                    },
                    "top_k":{
                        "type":"integer",
                        "description": "Number of sources to retrieve (default: 3, max: 5)",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5
                    }
                },
            }
        }
    }

def format_tool_response(sources: List[Dict]) -> str:
    """
    Format RAG sources for LLM consumption
    
    Returns a structured string the LLM can understand
    """
    if not sources:
        return "No relevant information found in the knowledge base."

    formatted = "Found the following sources:\n\n"
    source_refs = []

    for i, source in enumerate(sources, 1):
        filename = source.get('filename', 'Unknown')
        file_url = source.get('file_url', None)
        text = source.get('text', '')
        similarity = source.get('similarity', 0)
        
        # Show source with URL
        formatted += f"[{i}] {filename}"
        if file_url:
            formatted += f" - {file_url}"
        formatted += f" ({similarity:.0%} relevant)\n{text}\n\n"
        
        # Build citation reference
        if file_url:
            source_refs.append(f"[{i}] {filename}: {file_url}")
        else:
            source_refs.append(f"[{i}] {filename}")
    
    # Instructions with citation list
    formatted += "\n=== INSTRUCTIONS ===\n"
    formatted += "Answer using the sources above and include these citations:\n\n"
    for ref in source_refs:
        formatted += f"  {ref}\n"
    formatted += "\nAt the end of your response, add:\n"
    formatted += "\"\\n\\nSources:\\n\"\n"
    for ref in source_refs:
        formatted += f"  {ref}\n"
    
    return formatted
