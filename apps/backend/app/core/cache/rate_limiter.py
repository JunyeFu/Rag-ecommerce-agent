"""
滑动窗口限流器 - 替代模块级 defaultdict(deque)

封装限流计数逻辑，避免模块级可变状态。
"""
import time
import asyncio
from collections import deque
from collections import defaultdict


class SlidingWindowRateLimiter:
    """滑动窗口限流 - 线程安全 (asyncio.Lock)

    用法:
        limiter = SlidingWindowRateLimiter()
        allowed, retry_after = await limiter.check("ip:path", window=60, max_req=10)
    """

    def __init__(self):
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, window: int, max_req: int) -> tuple[bool, int]:
        """检查限流。返回 (allowed, remaining_seconds)."""
        now = time.time()
        async with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < now - window:
                bucket.popleft()
            if len(bucket) >= max_req:
                retry_after = int(bucket[0] + window - now) + 1
                return False, max(retry_after, 1)
            bucket.append(now)
            return True, 0

    async def cleanup_stale(self, max_age: int = 3600) -> None:
        """清理过期的 bucket（长时间未被访问的 key）"""
        now = time.time()
        async with self._lock:
            stale_keys = [
                k for k, v in self._buckets.items()
                if not v or v[-1] < now - max_age
            ]
            for k in stale_keys:
                del self._buckets[k]

    async def stats(self) -> dict:
        async with self._lock:
            return {"buckets": len(self._buckets)}
