"""缓存后端抽象 - 支持内存/Redis 等多种实现"""
import asyncio
import time
import logging
from collections import OrderedDict
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("cache")

MAX_SIZE = 100
TTL_SECONDS = 300


@runtime_checkable
class CacheBackend(Protocol):
    """通用缓存接口 - 无业务知识"""

    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def clear(self) -> None: ...
    async def stats(self) -> dict: ...


class InMemoryCache:
    """内存 LRU 缓存 - 线程安全 (asyncio.Lock)，带 TTL"""

    def __init__(self, max_size: int = MAX_SIZE, default_ttl: int = TTL_SECONDS):
        self._cache: OrderedDict[str, tuple[float, Any, int]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            if key in self._cache:
                ts, value, ttl = self._cache[key]
                if time.monotonic() - ts < ttl:
                    self._cache.move_to_end(key)
                    return value
                else:
                    del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        async with self._lock:
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._cache.popitem(last=False)
            self._cache[key] = (time.monotonic(), value, effective_ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def stats(self) -> dict:
        async with self._lock:
            return {"size": len(self._cache), "max": self._max_size, "ttl_s": self._default_ttl}


class NoOpCache:
    """空缓存 - 测试或禁用缓存时使用"""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def clear(self) -> None:
        pass

    async def stats(self) -> dict:
        return {"size": 0, "max": 0, "ttl_s": 0, "mode": "noop"}
