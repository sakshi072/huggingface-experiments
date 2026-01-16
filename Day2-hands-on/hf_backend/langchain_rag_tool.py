"""
LangChain RAG Tool using @tool decorator

Simpler, cleaner implementation wrapping your existing RAG service
"""
import logging
from langchain.tools import tool
from .rag_client import get_rag_client

logger = logging.getLogger(__name__)


@tool
async def search_knowledge_base(query: str, top_k: int = 3) -> str:
    """
    Search the company knowledge base for information.
    
    Use this when you need to:
    - Find company policies, procedures, or documentation
    - Look up technical details or specifications
    - Verify factual information about the company
    - Answer questions requiring specific domain knowledge

    Input should be a clear, specific search query.
    Returns relevant document excerpts with sources.
    
    Args:
        query: A clear, specific search query to find relevant documents
        top_k: Number of results to return (default: 3)
    
    Returns:
        Formatted search results with document excerpts and sources
    
    Example:
        search_knowledge_base("What is our vacation policy?", 3)
    """
    try:
        logger.info(f"🔍 Searching knowledge base: '{query}' (top_k={top_k})")
        
        # Get RAG client (reuses your existing client)
        rag_client = get_rag_client()
        
        # Search
        sources = await rag_client.search(query, top_k)
        
        if not sources:
            logger.warning("No sources found")
            return "No relevant documents found in the knowledge base."
        
        # Format results for LLM
        result = f"Found {len(sources)} relevant documents:\n\n"
        
        for i, source in enumerate(sources, 1):
            filename = source.get('filename', 'Unknown')
            similarity = source.get('similarity', 0)
            text = source.get('text', '').strip()
            file_url = source.get('file_url', '')
            
            result += f"**Document {i}: {filename}**\n"
            result += f"Relevance: {similarity:.1%}\n"
            
            if file_url:
                result += f"URL: {file_url}\n"
            
            result += f"\nContent:\n{text}\n"
            result += "\n" + "-" * 50 + "\n\n"
        
        logger.info(f"✅ Returned {len(sources)} sources for query: {query[:50]}...")
        return result
        
    except Exception as e:
        logger.error(f"❌ RAG search failed: {e}", exc_info=True)
        return f"Error searching knowledge base: {str(e)}"


# Optional: Keep backward compatibility
def get_rag_tool():
    """Get RAG search tool (for backward compatibility)"""
    return search_knowledge_base