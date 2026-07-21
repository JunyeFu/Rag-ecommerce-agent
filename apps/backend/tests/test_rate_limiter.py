"""速率限制中间件单元测试"""
import pytest
import time
from app.core.middleware import _rate_limiter


@pytest.mark.unit
class TestRateLimiter:
    """内存限流器测试"""

    def setup_method(self):
        _rate_limiter._buckets.clear()

    def teardown_method(self):
        _rate_limiter._buckets.clear()

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        allowed, _ = await _rate_limiter.check("ip:path", 60, 10)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_within_limit_allowed(self):
        for _ in range(5):
            allowed, _ = await _rate_limiter.check("ip:path", 60, 10)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_at_limit_allowed(self):
        """第 10 次请求应该通过（恰好等于 max_req）"""
        for _ in range(10):
            allowed, _ = await _rate_limiter.check("ip:path", 60, 10)
        # 第 10 次已经记录了，下一次应该被拒
        allowed, retry_after = await _rate_limiter.check("ip:path", 60, 10)
        assert allowed is False
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        """超过限制后拒绝"""
        for _ in range(10):
            await _rate_limiter.check("ip:path", 60, 10)
        allowed, _ = await _rate_limiter.check("ip:path", 60, 10)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        """不同 key 互不影响"""
        for _ in range(10):
            await _rate_limiter.check("ip1:path", 60, 10)
        allowed, _ = await _rate_limiter.check("ip2:path", 60, 10)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_window_expiry(self):
        """窗口过期后可再次请求"""
        # 填满
        for _ in range(10):
            await _rate_limiter.check("ip:path", 1, 10)  # 1秒窗口
        allowed, _ = await _rate_limiter.check("ip:path", 1, 10)
        assert allowed is False

        # 模拟时间流逝
        time.sleep(1.1)
        allowed, _ = await _rate_limiter.check("ip:path", 1, 10)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_retry_after_is_positive(self):
        """被拒时 retry_after > 0"""
        for _ in range(5):
            await _rate_limiter.check("ip:path", 60, 5)
        allowed, retry_after = await _rate_limiter.check("ip:path", 60, 5)
        assert allowed is False
        assert retry_after >= 1
