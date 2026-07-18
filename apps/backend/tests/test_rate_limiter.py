"""速率限制中间件单元测试"""
import pytest
import time
from app.core.middleware import _check_rate_limit, _rate_buckets


@pytest.mark.unit
class TestRateLimiter:
    """内存限流器测试"""

    def setup_method(self):
        _rate_buckets.clear()

    def test_first_request_allowed(self):
        allowed, _ = _check_rate_limit("ip:path", 60, 10)
        assert allowed is True

    def test_within_limit_allowed(self):
        for _ in range(5):
            allowed, _ = _check_rate_limit("ip:path", 60, 10)
        assert allowed is True

    def test_at_limit_allowed(self):
        """第 10 次请求应该通过（恰好等于 max_req）"""
        for _ in range(10):
            allowed, _ = _check_rate_limit("ip:path", 60, 10)
        # 第 10 次已经记录了，下一次应该被拒
        allowed, retry_after = _check_rate_limit("ip:path", 60, 10)
        assert allowed is False
        assert retry_after > 0

    def test_over_limit_blocked(self):
        """超过限制后拒绝"""
        for _ in range(10):
            _check_rate_limit("ip:path", 60, 10)
        allowed, _ = _check_rate_limit("ip:path", 60, 10)
        assert allowed is False

    def test_different_keys_independent(self):
        """不同 key 互不影响"""
        for _ in range(10):
            _check_rate_limit("ip1:path", 60, 10)
        allowed, _ = _check_rate_limit("ip2:path", 60, 10)
        assert allowed is True

    def test_window_expiry(self):
        """窗口过期后可再次请求"""
        # 填满
        for _ in range(10):
            _check_rate_limit("ip:path", 1, 10)  # 1秒窗口
        allowed, _ = _check_rate_limit("ip:path", 1, 10)
        assert allowed is False

        # 模拟时间流逝
        time.sleep(1.1)
        allowed, _ = _check_rate_limit("ip:path", 1, 10)
        assert allowed is True

    def test_retry_after_is_positive(self):
        """被拒时 retry_after > 0"""
        for _ in range(5):
            _check_rate_limit("ip:path", 60, 5)
        allowed, retry_after = _check_rate_limit("ip:path", 60, 5)
        assert allowed is False
        assert retry_after >= 1
