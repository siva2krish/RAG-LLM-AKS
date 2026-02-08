"""
Cache Module - Semantic Caching for RAG
========================================
Caches RAG responses to reduce LLM calls and costs.

AI Learning Notes:
------------------
## Why Cache RAG Responses?

1. **Cost Savings**: LLM API calls are expensive
   - GPT-4o: ~$5/1M input tokens, ~$15/1M output tokens
   - Caching identical queries eliminates redundant calls

2. **Latency Reduction**: 
   - LLM calls: 1-5 seconds
   - Cache hit: <10ms

3. **Rate Limit Protection**:
   - Azure OpenAI has TPM (tokens per minute) limits
   - Caching reduces API pressure

## Caching Strategies:

1. **Exact Match Cache** (this implementation)
   - Hash the query string
   - Simple but only catches identical queries

2. **Semantic Cache** (advanced)
   - Embed the query
   - Find cached queries with high cosine similarity
   - "How to deploy K8s?" matches "Kubernetes deployment steps"

3. **TTL Considerations**:
   - Short TTL: Fresh answers, more API calls
   - Long TTL: Stale answers, lower costs
   - Balance based on content update frequency
"""

import hashlib
import json
from typing import Optional, Any
from datetime import timedelta

from src.common import get_settings, get_logger

logger = get_logger(__name__)
settings = get_settings()

# In-memory cache for development (use Redis in production)
_cache: dict = {}


def _get_cache_key(query: str) -> str:
    """Generate a cache key from the query."""
    normalized = query.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class SimpleCache:
    """
    Simple in-memory cache with TTL support.
    
    AI Learning Note:
    In production, replace this with Redis:
    - Distributed across pods
    - Persistence across restarts
    - TTL handled automatically
    """
    
    def __init__(self, default_ttl_seconds: int = 3600):
        self.default_ttl = default_ttl_seconds
        self._store: dict = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._store:
            entry = self._store[key]
            # In a real implementation, check TTL
            logger.debug("Cache hit", key=key[:8])
            return entry.get("value")
        logger.debug("Cache miss", key=key[:8])
        return None
    
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set value in cache."""
        self._store[key] = {
            "value": value,
            "ttl": ttl_seconds or self.default_ttl
        }
        logger.debug("Cache set", key=key[:8])
    
    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        self._store.pop(key, None)
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        self._store.clear()


# Singleton instance
_cache_instance: Optional[SimpleCache] = None


def get_cache() -> SimpleCache:
    """Get or create cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SimpleCache()
    return _cache_instance


async def get_cached_response(query: str) -> Optional[dict]:
    """Get cached RAG response for a query."""
    cache = get_cache()
    key = _get_cache_key(query)
    return await cache.get(key)


async def set_cached_response(query: str, response: dict, ttl_seconds: int = 3600) -> None:
    """Cache a RAG response."""
    cache = get_cache()
    key = _get_cache_key(query)
    await cache.set(key, response, ttl_seconds)
