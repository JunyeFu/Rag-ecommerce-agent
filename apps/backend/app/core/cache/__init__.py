"""缓存模块 - 公开接口

用法:
    from app.core.cache import query_cache, InMemoryCache, NoOpCache, CacheBackend

向后兼容:
    from app.services.cache import get, set, stats, clear  # 仍然可用
"""
from app.core.cache.backend import CacheBackend, InMemoryCache, NoOpCache
from app.core.cache.query_cache import QueryCache, query_cache
from app.core.cache.rate_limiter import SlidingWindowRateLimiter

__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "NoOpCache",
    "QueryCache",
    "query_cache",
    "SlidingWindowRateLimiter",
]
