import hashlib
import json
import redis.asyncio as redis

# Initialize Redis
redis_client = redis.from_url("redis://redis:6379", decode_responses=True)

class SearchCache:
    """Redis cache for frequent queries"""
    @staticmethod
    def _generate_key(query:str) -> str:
        # Normalize query: lowercase and strip to increase hit rate
        normalized_query = query.lower().strip()
        query_hash = hashlib.md5(normalized_query.encode()).hexdigest()
        return f"search_cache:{query_hash}"

    @classmethod
    async def get(cls, query:str):
        key = cls._generate_key(query)
        data = await redis_client.get(key)
        return json.loads(data) if data else None
    
    @classmethod
    async def set(cls, query:str, results:dict, ttl:int = 3600):
        key = cls._generate_key(query)
        await redis_client.setex(key, ttl, json.dumps(results))
    
    # @classmethod 
    # async def invalidate_domain(cls, domain_name:str):
    #     # Clears all cached searches for a specific domain
    #     async for key in redis_client.scan_iter(f"search_cache:{domain_name}:*"):
    #         await redis_client.delete(key)

