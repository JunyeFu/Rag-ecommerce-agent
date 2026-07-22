"""查询缓存 - 域专用包装层

在通用 CacheBackend 之上添加:
- 动态查询检测 (购物车等不缓存)
- 缓存版本控制 (参数变更时自动失效)
"""
import hashlib
import logging
from typing import Any

from app.core.cache.backend import CacheBackend, InMemoryCache

logger = logging.getLogger("cache")

# 缓存版本 - 参数变更时递增，自动失效旧缓存
CACHE_VERSION = 3

# 动态查询关键词 - 命中则不缓存
SKIP_CACHE_KEYWORDS = ["购物车", "加购", "加到购物车", "加入购物车", "查看购物车", "清空购物车", "下单"]


def _is_dynamic(query: str) -> bool:
    """是否为动态查询（购物车等）- 此类查询不应缓存"""
    return any(kw in query for kw in SKIP_CACHE_KEYWORDS)


def _key(query: str, cache_key: str | None = None) -> str:
    raw = cache_key if cache_key is not None else query
    return hashlib.md5(raw.strip().lower().encode()).hexdigest()


class QueryCache:
    """域专用查询缓存 - 包装 CacheBackend，添加业务逻辑"""

    def __init__(self, backend: CacheBackend):
        self._backend = backend

    async def get(self, query: str, cache_key: str | None = None) -> dict | None:
        """查询缓存，返回 {response, cards, _v} 或 None"""
        if _is_dynamic(query):
            return None
        k = _key(query, cache_key)
        value = await self._backend.get(k)
        if value is not None:
            if isinstance(value, dict) and value.get("_v") != CACHE_VERSION:
                await self._backend.delete(k)
                logger.debug("Cache STALE (v%s != v%d): %s", value.get("_v", 0), CACHE_VERSION, query[:30])
                return None
            logger.debug("Cache HIT: %s", query[:30])
            return value
        return None

    async def set(self, query: str, response: str, cards: list, cache_key: str | None = None) -> None:
        """写入缓存"""
        if _is_dynamic(query):
            return
        k = _key(query, cache_key)
        value = {"response": response, "cards": cards, "_v": CACHE_VERSION}
        await self._backend.set(k, value)
        logger.debug("Cache SET: %s", query[:30])

    async def stats(self) -> dict:
        return await self._backend.stats()

    async def clear(self) -> None:
        await self._backend.clear()


# 全局单例 - 默认使用 InMemoryCache
_default_backend = InMemoryCache()
query_cache = QueryCache(_default_backend)
