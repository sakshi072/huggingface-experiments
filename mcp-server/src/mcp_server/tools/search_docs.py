from mcp_server.models.search_models import SearchKnowledgeBaseArgs
import httpx
from mcp_server.core.settings import settings
from mcp_server.middleware.auth import get_token

async def search_knowledge_base(args: SearchKnowledgeBaseArgs) -> str:
    """Semantic search across all documents available."""
    token = await get_token()

    async with httpx.AsyncClient(base_url=str(settings.RETRIEVAL_BASE_URL), timeout=30.0) as client:
        response = await client.post(
            "/search",
            json={"query": args.query, "top_k": args.top_k},
            headers={"Authorization":f"Bearer {token}"}
        )
        return response.text