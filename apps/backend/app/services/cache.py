"""
查询缓存 - 向后兼容 facade

实际实现已迁移到 app.core.cache 包:
  - CacheBackend Protocol + InMemoryCache -> app.core.cache.backend
  - QueryCache (域专用包装) -> app.core.cache.query_cache

本文件保持原 API 不变，现有 import 无需修改。
"""
from app.core.cache.query_cache import query_cache as _qc

async def get(query: str, cache_key: str | None = None) -> dict | None:
    """查询缓存，返回 {response, cards, _v} 或 None"""
    return await _qc.get(query, cache_key)


async def set(query: str, response: str, cards: list, cache_key: str | None = None):
    """写入缓存"""
    await _qc.set(query, response, cards, cache_key)


async def stats() -> dict:
    """缓存统计"""
    return await _qc.stats()


async def clear():
    await _qc.clear()
