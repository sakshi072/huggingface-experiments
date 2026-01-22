
import json
import redis.asyncio as redis
import logging
from app.schemas import SearchResult

logger = logging.getLogger(__name__)

# Initialize Redis
redis_client = redis.from_url("redis://redis:6379", decode_responses=True)

class SearchCache:
    """Redis cache for frequent search query results"""

    @classmethod
    async def get(cls, search_id:str):
        try:
            data = await redis_client.get(search_id)
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning(f"Redis GET failed: {e}. Falling back to DB")
            return None
    
    @classmethod
    async def set(cls, search_id:str, results:SearchResult, ttl:int = 3600):
        try:
            await redis_client.setex(search_id, ttl, json.dumps(results))
        except Exception as e:
            logger.warning(f"Redis SET failed: {e}")
    
    # @classmethod 
    # async def invalidate_domain(cls, domain_name:str):
    #     # Clears all cached searches for a specific domain
    #     async for key in redis_client.scan_iter(f"search_cache:{domain_name}:*"):
    #         await redis_client.delete(key)

