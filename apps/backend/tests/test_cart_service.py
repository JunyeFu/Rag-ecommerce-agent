"""购物车服务单元测试 - 缓存逻辑 + CRUD + user_id 过滤"""
import pytest
import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock
from app.services import cart_service
from app.services.cart_service import (
    _cart_cache,
    _cache_key,
    _invalidate_cache,
    get_cart,
    get_cart_total,
    add_to_cart,
    remove_from_cart,
    clear_cart,
)
from app.core.exceptions import BadRequestError

VALID_SESSION = str(_uuid.uuid4())


@pytest.mark.unit
class TestCacheKey:
    """缓存键生成测试"""

    def test_cache_key_without_user(self):
        assert _cache_key("s1", "") == "s1"

    def test_cache_key_with_user(self):
        assert _cache_key("s1", "u1") == "s1:u1"

    def test_cache_key_none_user(self):
        assert _cache_key("s1", None) == "s1"


@pytest.mark.unit
class TestInvalidateCache:
    """缓存失效逻辑测试"""

    def setup_method(self):
        _cart_cache._cache.clear()

    def teardown_method(self):
        _cart_cache._cache.clear()

    @pytest.mark.asyncio
    async def test_invalidate_removes_exact_key(self):
        await _cart_cache.set("s1", ([], 0.0))
        await _invalidate_cache("s1")
        assert await _cart_cache.get("s1") is None

    @pytest.mark.asyncio
    async def test_invalidate_removes_all_user_variants(self):
        await _cart_cache.set("s1", ([], 0.0))
        await _cart_cache.set("s1:u1", ([], 0.0))
        await _cart_cache.set("s1:u2", ([], 0.0))
        await _invalidate_cache("s1")
        assert await _cart_cache.get("s1") is None
        assert await _cart_cache.get("s1:u1") is None
        assert await _cart_cache.get("s1:u2") is None

    @pytest.mark.asyncio
    async def test_invalidate_does_not_match_prefix_overlap(self):
        await _cart_cache.set("s1", ([], 0.0))
        await _cart_cache.set("s1extra", ([], 0.0))
        await _invalidate_cache("s1")
        assert await _cart_cache.get("s1") is None
        assert await _cart_cache.get("s1extra") is not None

    @pytest.mark.asyncio
    async def test_invalidate_preserves_other_sessions(self):
        await _cart_cache.set("s1", ([], 0.0))
        await _cart_cache.set("s2", ([], 0.0))
        await _invalidate_cache("s1")
        assert await _cart_cache.get("s2") is not None


@pytest.mark.unit
class TestGetCart:
    """get_cart 测试 - 缓存命中/未命中 + user_id 过滤"""

    def setup_method(self):
        _cart_cache._cache.clear()

    def teardown_method(self):
        _cart_cache._cache.clear()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        item = MagicMock()
        item.price = 10.0
        item.quantity = 2
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [item]
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_cart(db, VALID_SESSION)
        assert result == [item]
        assert db.execute.called

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        item = MagicMock()
        await _cart_cache.set(VALID_SESSION, ([item], 20.0))
        db = MagicMock()
        db.execute = AsyncMock()

        result = await get_cart(db, VALID_SESSION)
        assert result == [item]
        assert not db.execute.called

    @pytest.mark.asyncio
    async def test_cache_stored_with_correct_total(self):
        item = MagicMock()
        item.price = 10.0
        item.quantity = 3
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [item]
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        await get_cart(db, VALID_SESSION)
        cached = await _cart_cache.get(VALID_SESSION)
        assert cached is not None
        assert cached[1] == 30.0

    @pytest.mark.asyncio
    async def test_user_id_uses_composite_cache_key(self):
        await _cart_cache.set(f"{VALID_SESSION}:u1", ([], 0.0))
        db = MagicMock()
        db.execute = AsyncMock()

        result = await get_cart(db, VALID_SESSION, user_id="u1")
        assert result == []
        assert not db.execute.called


@pytest.mark.unit
class TestGetCartTotal:
    """get_cart_total 测试 - 缓存命中/未命中"""

    def setup_method(self):
        _cart_cache._cache.clear()

    def teardown_method(self):
        _cart_cache._cache.clear()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        result_mock = MagicMock()
        result_mock.scalar.return_value = 42.5
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        total = await get_cart_total(db, VALID_SESSION)
        assert total == 42.5

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_total(self):
        await _cart_cache.set(VALID_SESSION, ([], 99.9))
        db = MagicMock()
        db.execute = AsyncMock()

        total = await get_cart_total(db, VALID_SESSION)
        assert total == 99.9
        assert not db.execute.called

    @pytest.mark.asyncio
    async def test_empty_cart_returns_zero(self):
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        total = await get_cart_total(db, VALID_SESSION)
        assert total == 0.0


@pytest.mark.unit
class TestRemoveFromCart:
    """remove_from_cart 测试"""

    def setup_method(self):
        _cart_cache._cache.clear()

    def teardown_method(self):
        _cart_cache._cache.clear()

    @pytest.mark.asyncio
    async def test_remove_existing_item(self):
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        ok = await remove_from_cart(db, VALID_SESSION, "prod-1")
        assert ok is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_item(self):
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        ok = await remove_from_cart(db, VALID_SESSION, "missing")
        assert ok is False

    @pytest.mark.asyncio
    async def test_remove_invalidates_cache(self):
        await _cart_cache.set(VALID_SESSION, ([], 0.0))
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        await remove_from_cart(db, VALID_SESSION, "prod-1")
        assert await _cart_cache.get(VALID_SESSION) is None


@pytest.mark.unit
class TestClearCart:
    """clear_cart 测试"""

    def setup_method(self):
        _cart_cache._cache.clear()

    def teardown_method(self):
        _cart_cache._cache.clear()

    @pytest.mark.asyncio
    async def test_clear_executes_delete(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        await clear_cart(db, VALID_SESSION)
        assert db.execute.called

    @pytest.mark.asyncio
    async def test_clear_invalidates_cache(self):
        await _cart_cache.set(VALID_SESSION, ([], 0.0))
        await _cart_cache.set(f"{VALID_SESSION}:u1", ([], 0.0))
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        await clear_cart(db, VALID_SESSION)
        assert await _cart_cache.get(VALID_SESSION) is None
        assert await _cart_cache.get(f"{VALID_SESSION}:u1") is None
