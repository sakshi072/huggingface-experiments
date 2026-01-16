"""
Web Search Integration for Job Discovery

This module provides the web search functionality needed by the job search tool.
It can be integrated with various search APIs (Tavily, SerpAPI, etc.)
"""

import os
import logging
from typing import List, Dict, Optional
import httpx
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

class WebSearchClient:
    """
    Web search client for job discovery
    
    Supports multiple search providers:
    - Tavily AI Search API (recommended for AI apps)
    - SerpAPI (Google search results)
    - Bing Search API
    """

    def __init__(self, provider:str = "tavily"):
        """
        Initialize web search client
        
        Args:
            provider: Search provider ('tavily', 'serpapi', 'bing')
        """
        self.provider = provider
        self.api_key = self._get_api_key()

        if not self.api_key:
            logger.warning(f"⚠️ No API key found for {provider}")
        
        logger.info(f"🔍 Web search client initialized: {provider}")

    def _get_api_key(self) -> Optional[str]:
        """Get API key for selected provider"""
        key_map = {
            "tavily": "TAVILY_API_KEY",
            "serpapi": "SERPAPI_API_KEY",
            "bing": "BING_SEARCH_API_KEY"
        }

        env_var = key_map.get(self.provider)
        if not env_var:
            return None
        return os.getenv(env_var)

    async def search(
        self,
        query:str,
        max_result: int = 5,
        search_depth:str = "basic"
    )-> List[Dict]:
        """
        Execute web search
        
        Args:
            query: Search query
            max_results: Maximum results to return
            search_depth: Search depth ('basic' or 'advanced')
            
        Returns:
            List of search results with title, url, snippet
        """
        if self.provider == "tavily":
            return await self._search_tavily(query, max_result, search_depth)
        elif self.provider == "serpapi":
            return await self._search_serpapi(query, max_result)
        elif self.provider == "bing":
            return await self._search_bing(query, max_result)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
    async def _search_tavily(
        self,
        query:str,
        max_results:int,
        search_depth:str
    ) ->List[Dict]:
        """
        Search using Tavily AI Search API
        
        Tavily is optimized for AI applications and provides
        clean, relevant results perfect for RAG systems.
        
        Get API key: https://tavily.com
        """
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY not set")
        
        logger.info(f"🔍 Tavily search: {query}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json = {
                        "api_key":self.api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": search_depth,
                        "include_answer": False,
                        "include_raw_content": False,
                        "include_images": False
                    }
                )

                response.raise_for_status()
                data = response.json()
                logger.info(f"in tavily: {data}")
                # Parse Tavily results
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                        "score": item.get("score", 0)
                    })

                logger.info(f"✅ Tavily returned {len(results)} results")
                return results
        except httpx.HTTPError as e:
            logger.error(f"❌ Tavily search failed: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return []
    
    async def _search_serpapi(
        self,
        query: str,
        max_results: int
    ) -> List[Dict]:
        """
        Search using SerpAPI (Google Search Results)
        
        SerpAPI provides real Google search results with
        rich metadata.
        
        Get API key: https://serpapi.com
        """
        pass
    
    async def _search_bing(
        self,
        query: str,
        max_results: int
    ) -> List[Dict]:
        """
        Search using Bing Search API
        
        Microsoft's Bing Search API provides comprehensive
        search results.
        
        Get API key: https://azure.microsoft.com/en-us/services/cognitive-services/bing-web-search-api/
        """
        pass

# Global search client instance
_search_client: Optional[WebSearchClient] = None

def get_search_client(provider:str ="tavily") -> WebSearchClient:
    """
    Get global search client instance (singleton)
    
    Args:
        provider: Search provider
        
    Returns:
        WebSearchClient instance
    """
    global _search_client
    if not _search_client:
        _search_client = WebSearchClient(provider=provider)
    
    return _search_client

async def search_web(query: str, max_results: int = 5) -> List[Dict]:
    """
    Convenience function for web search
    
    Args:
        query: Search query
        max_results: Max results to return
        
    Returns:
        Search results
    """
    client = get_search_client()
    return await client.search(query, max_results)