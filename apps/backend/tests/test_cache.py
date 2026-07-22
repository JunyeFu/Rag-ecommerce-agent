import asyncio

import pytest
from app.core.cache.backend import InMemoryCache, NoOpCache
from app.core.cache.query_cache import QueryCache, _is_dynamic, _key, CACHE_VERSION


@pytest.mark.unit
class TestInMemoryCache:
    async def test_get_miss_returns_none(self):
        cache = InMemoryCache(max_size=10)
        assert await cache.get("missing") is None

    async def test_set_then_get_returns_value(self):
        cache = InMemoryCache(max_size=10)
        await cache.set("key", "value")
        assert await cache.get("key") == "value"

    async def test_lru_eviction_at_max_size(self):
        cache = InMemoryCache(max_size=2)
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.set("k3", "v3")
        assert await cache.get("k1") is None
        assert await cache.get("k2") == "v2"
        assert await cache.get("k3") == "v3"

    async def test_lru_eviction_order_after_get(self):
        cache = InMemoryCache(max_size=2)
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.get("k1")
        await cache.set("k3", "v3")
        assert await cache.get("k1") == "v1"
        assert await cache.get("k2") is None

    async def test_clear_empties_all(self):
        cache = InMemoryCache(max_size=10)
        await cache.set("k1", "v1")
        await cache.clear()
        assert await cache.get("k1") is None

    async def test_delete_removes_key(self):
        cache = InMemoryCache(max_size=10)
        await cache.set("k1", "v1")
        await cache.delete("k1")
        assert await cache.get("k1") is None

    async def test_delete_missing_key_no_error(self):
        cache = InMemoryCache(max_size=10)
        await cache.delete("nonexistent")

    async def test_overwrite_existing_key(self):
        cache = InMemoryCache(max_size=10)
        await cache.set("k1", "v1")
        await cache.set("k1", "v2")
        assert await cache.get("k1") == "v2"

    async def test_overwrite_does_not_evict(self):
        cache = InMemoryCache(max_size=2)
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.set("k1", "v1_updated")
        assert await cache.get("k1") == "v1_updated"
        assert await cache.get("k2") == "v2"

    async def test_stats_returns_correct_info(self):
        cache = InMemoryCache(max_size=5, default_ttl=60)
        await cache.set("k1", "v1")
        stats = await cache.stats()
        assert stats["size"] == 1
        assert stats["max"] == 5
        assert stats["ttl_s"] == 60

    async def test_stats_empty_cache(self):
        cache = InMemoryCache(max_size=10)
        stats = await cache.stats()
        assert stats["size"] == 0

    async def test_ttl_expiration(self):
        cache = InMemoryCache(max_size=10, default_ttl=1)
        await cache.set("k1", "v1", ttl=0)
        await asyncio.sleep(0.01)
        assert await cache.get("k1") is None

    async def test_custom_ttl_overrides_default(self):
        cache = InMemoryCache(max_size=10, default_ttl=0)
        await cache.set("k1", "v1", ttl=300)
        assert await cache.get("k1") == "v1"

    async def test_default_ttl_expires(self):
        cache = InMemoryCache(max_size=10, default_ttl=0)
        await cache.set("k1", "v1")
        await asyncio.sleep(0.01)
        assert await cache.get("k1") is None

    async def test_get_moves_to_end_lru(self):
        cache = InMemoryCache(max_size=3)
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.set("k3", "v3")
        await cache.get("k1")
        await cache.set("k4", "v4")
        assert await cache.get("k1") == "v1"
        assert await cache.get("k2") is None

    async def test_various_value_types(self):
        cache = InMemoryCache(max_size=10)
        await cache.set("str", "hello")
        await cache.set("int", 42)
        await cache.set("list", [1, 2, 3])
        await cache.set("dict", {"a": 1})
        await cache.set("none", None)
        assert await cache.get("str") == "hello"
        assert await cache.get("int") == 42
        assert await cache.get("list") == [1, 2, 3]
        assert await cache.get("dict") == {"a": 1}
        assert await cache.get("none") is None


@pytest.mark.unit
class TestNoOpCache:
    async def test_get_always_none(self):
        cache = NoOpCache()
        assert await cache.get("anything") is None

    async def test_set_no_error(self):
        cache = NoOpCache()
        await cache.set("key", "value")

    async def test_delete_no_error(self):
        cache = NoOpCache()
        await cache.delete("key")

    async def test_clear_no_error(self):
        cache = NoOpCache()
        await cache.clear()

    async def test_stats(self):
        cache = NoOpCache()
        stats = await cache.stats()
        assert stats["size"] == 0
        assert stats["mode"] == "noop"


@pytest.mark.unit
class TestIsDynamic:
    def test_cart_keyword_is_dynamic(self):
        assert _is_dynamic("查看购物车") is True

    def test_add_to_cart_is_dynamic(self):
        assert _is_dynamic("加入购物车") is True

    def test_checkout_is_dynamic(self):
        assert _is_dynamic("下单") is True

    def test_normal_query_not_dynamic(self):
        assert _is_dynamic("推荐蓝牙耳机") is False

    def test_empty_query_not_dynamic(self):
        assert _is_dynamic("") is False


@pytest.mark.unit
class TestKey:
    def test_key_is_md5_hash(self):
        k = _key("test query")
        assert len(k) == 32

    def test_key_strips_and_lowercases(self):
        assert _key("  Test Query  ") == _key("test query")

    def test_key_uses_cache_key_when_provided(self):
        k1 = _key("query1", cache_key="custom_key")
        k2 = _key("query2", cache_key="custom_key")
        assert k1 == k2

    def test_different_queries_different_keys(self):
        assert _key("query1") != _key("query2")


@pytest.mark.unit
class TestQueryCache:
    async def test_set_then_get(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("推荐耳机", "好的推荐", [{"id": 1}])
        result = await qc.get("推荐耳机")
        assert result is not None
        assert result["response"] == "好的推荐"
        assert result["cards"] == [{"id": 1}]
        assert result["_v"] == CACHE_VERSION

    async def test_dynamic_query_get_returns_none(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("查看购物车", "response", [])
        result = await qc.get("查看购物车")
        assert result is None

    async def test_dynamic_query_set_is_noop(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("加入购物车", "response", [])
        result = await qc.get("加入购物车")
        assert result is None

    async def test_miss_returns_none(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        result = await qc.get("never cached query")
        assert result is None

    async def test_custom_cache_key(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("query", "response", [], cache_key="custom_cache_key")
        result = await qc.get("query", cache_key="custom_cache_key")
        assert result is not None
        assert result["response"] == "response"

    async def test_different_cache_keys_different_results(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("query", "response1", [], cache_key="key1")
        await qc.set("query", "response2", [], cache_key="key2")
        r1 = await qc.get("query", cache_key="key1")
        r2 = await qc.get("query", cache_key="key2")
        assert r1["response"] == "response1"
        assert r2["response"] == "response2"

    async def test_stats_passthrough(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("query", "response", [])
        stats = await qc.stats()
        assert stats["size"] == 1

    async def test_clear_passthrough(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        await qc.set("query", "response", [])
        await qc.clear()
        result = await qc.get("query")
        assert result is None

    async def test_version_mismatch_invalidates(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        raw_key = _key("test query")
        await backend.set(raw_key, {"response": "old", "cards": [], "_v": 0})
        result = await qc.get("test query")
        assert result is None

    async def test_version_mismatch_deletes_stale(self):
        backend = InMemoryCache(max_size=10)
        qc = QueryCache(backend)
        raw_key = _key("test query")
        await backend.set(raw_key, {"response": "old", "cards": [], "_v": 0})
        await qc.get("test query")
        assert await backend.get(raw_key) is None
