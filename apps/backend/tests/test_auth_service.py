"""认证服务单元测试 - Session Token 生成/验证/缓存/撤销"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.auth_service import (
    _TOKEN_TTL,
    _cache_get,
    _cache_set,
    _cache_del,
    _cache_clear,
    create_session_token,
    validate_session_token,
    revoke_session_token,
)


@pytest.mark.unit
class TestTokenCache:
    """内存缓存测试"""

    def setup_method(self):
        _cache_clear()

    def test_cache_set_and_get(self):
        _cache_set("token-1", "user-1")
        assert _cache_get("token-1") == "user-1"

    def test_cache_get_miss_returns_none(self):
        assert _cache_get("nonexistent") is None

    def test_cache_del_removes_entry(self):
        _cache_set("token-1", "user-1")
        _cache_del("token-1")
        assert _cache_get("token-1") is None

    def test_cache_clear_removes_all(self):
        _cache_set("token-1", "user-1")
        _cache_set("token-2", "user-2")
        _cache_clear()
        assert _cache_get("token-1") is None
        assert _cache_get("token-2") is None

    def test_cache_expired_entry_returns_none(self):
        _cache_set("token-1", "user-1", ttl=-1)
        assert _cache_get("token-1") is None

    def test_cache_overwrite(self):
        _cache_set("token-1", "user-1")
        _cache_set("token-1", "user-2")
        assert _cache_get("token-1") == "user-2"


@pytest.mark.unit
class TestCreateSessionToken:
    """Token 生成测试 - 内存模式"""

    @pytest.mark.asyncio
    async def test_create_guest_token_memory_mode(self):
        """内存模式 - 创建游客 token"""
        with patch("app.core.database.AsyncSessionLocal", None):
            token, user_id, is_guest, expires_at = await create_session_token()
            assert token
            assert user_id.startswith("guest-")
            assert is_guest is True
            assert expires_at is not None

    @pytest.mark.asyncio
    async def test_create_token_with_user_id_memory_mode(self):
        """内存模式 - 传入 user_id 创建关联 token"""
        with patch("app.core.database.AsyncSessionLocal", None):
            token, user_id, is_guest, _ = await create_session_token(
                user_id="existing-user-1", nickname="Test"
            )
            assert token
            assert user_id == "existing-user-1"
            assert is_guest is False

    @pytest.mark.asyncio
    async def test_create_token_is_uuid_format(self):
        with patch("app.core.database.AsyncSessionLocal", None):
            token, _, _, _ = await create_session_token()
            import uuid
            parsed = uuid.UUID(token)
            assert str(parsed) == token

    @pytest.mark.asyncio
    async def test_create_token_caches_token(self):
        """生成的 token 写入缓存"""
        with patch("app.core.database.AsyncSessionLocal", None):
            _cache_clear()
            token, user_id, _, _ = await create_session_token()
            assert _cache_get(token) == user_id


@pytest.mark.unit
class TestValidateSessionToken:
    """Token 验证测试"""

    @pytest.mark.asyncio
    async def test_validate_cached_token(self):
        """缓存命中的 token 返回 user_id"""
        _cache_set("valid-token", "user-1")
        result = await validate_session_token("valid-token")
        assert result == "user-1"

    @pytest.mark.asyncio
    async def test_validate_unknown_token_memory_mode(self):
        """内存模式下未知 token 返回 None"""
        _cache_clear()
        with patch("app.core.database.AsyncSessionLocal", None):
            result = await validate_session_token("unknown-token")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_expired_cached_token(self):
        """过期的缓存 token 返回 None"""
        _cache_set("expired", "user-1", ttl=-1)
        with patch("app.core.database.AsyncSessionLocal", None):
            result = await validate_session_token("expired")
            assert result is None


@pytest.mark.unit
class TestRevokeSessionToken:
    """Token 撤销测试"""

    @pytest.mark.asyncio
    async def test_revoke_cached_token(self):
        """撤销缓存中的 token"""
        _cache_set("revoke-me", "user-1")
        with patch("app.services.auth_service.AsyncSessionLocal", None):
            ok = await revoke_session_token("revoke-me")
        assert ok is True
        assert _cache_get("revoke-me") is None

    @pytest.mark.asyncio
    async def test_revoke_unknown_token_memory_mode(self):
        """内存模式下撤销未知 token 仍返回 True"""
        with patch("app.services.auth_service.AsyncSessionLocal", None):
            ok = await revoke_session_token("nonexistent")
        assert ok is True
