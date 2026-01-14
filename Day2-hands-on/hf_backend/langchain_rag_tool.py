"""
LangChain RAG Tool

Wraps your existing RAG service as a LangChain tool
"""
import logging
from typing import List,Dict,Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from .rag_client import get_rag_client

logger = logging.getLogger(__name__)

class RAGSearchInput(BaseModel):
    """Input schema for RAG search tool"""
    query:str = Field(description="The search qyery to find relevant documents")
    top_k:int = Field(default=3, description="Number of results to return")

class RAGSearchTool(BaseTool):
    """
    RAG Knowledge Base Search Tool
    
    Allows LangChain agents to search your company's knowledge base.
    """

    name:str = "search_knowledge_base"
    description:str = """Search the company knowledge base for information.
    
    Use this when you need to:
    - Find company policies, procedures, or documentation
    - Look up technical details or specifications
    - Verify factual information about the company
    - Answer questions requiring specific domain knowledge

    Input should be a clear, specific search query.
    Returns relevant document excerpts with sources."""

    args_schema: type[BaseModel] = RAGSearchInput

    def _run(self, query: str, top_k: int = 3) -> str:
        """Sync implementation required by LangChain"""
        raise NotImplementedError("Use _arun for this tool")

    async def _arun(self, query:str, top_k:int=3) -> str:
        """
        Async search (used by LangChain agents)
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            Formatted search results with sources
        """
        try:
            # Get RAG client
            rag_client = get_rag_client()

            # Search
            sources = await rag_client.search(query, top_k)

            if not sources:
                return "No relevant documents found in the knowledge base."
            
            # Format results for LLM
            result = f"Found {len(sources)} relevant documents:\n\n"

            for i, source in enumerate(sources):
                filename = source.get('filename', 'Unknown')
                similarity = source.get('similarity', 0)
                text = source.get('text', '')
                file_url = source.get('file_url', '')

                result += f"Document {i}: {filename} (Relevance: {similarity:.0%})\n"
                if file_url:
                    result += f"URL: {file_url}\n"
                result += f"Content: {text}\n\n"
            
            logger.info(f"🔍 RAG tool returned {len(sources)} sources for: {query[:50]}...")

            return result

        except Exception as e:
            logger.error(f"RAG tool error: {e}")
            return f"Error searching knowledge base: {str(e)}"

def get_rag_tool() -> RAGSearchTool:
    """Get RAG search tool instance"""
    return RAGSearchTool()
