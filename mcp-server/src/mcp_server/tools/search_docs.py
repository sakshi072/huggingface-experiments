import httpx
from mcp_server.core.settings import settings
from mcp_server.middleware.auth import get_token
from typing import Annotated
from pydantic import Field


async def search_knowledge_base(
    query: Annotated[str, Field(description="The search query string", min_length=1)],
    top_k: Annotated[int, Field(default=3, gt=0, le=10, description="Number of results to return")]
) -> str:
    """Semantic search across all documents available."""
    token = await get_token()

    async with httpx.AsyncClient(base_url=str(settings.RETRIEVAL_BASE_URL), timeout=30.0) as client:
        response = await client.post(
            "/search",
            json={"query": query, "top_k": top_k or 3},
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.text