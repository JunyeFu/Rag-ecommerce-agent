import pytest
pytestmark = pytest.mark.integration

"""
RAG retrieval structure tests
"""
import pytest


def test_chunk_structure():
    """验证检索 chunk 数据结构完整性"""
    chunk = {
        "chunk_id": "test-1",
        "text": "Test product description",
        "metadata": {"product_id": "p1", "category": "test"},
    }
    assert "chunk_id" in chunk
    assert "text" in chunk
    assert "metadata" in chunk

def test_chunk_metadata_fields():
    chunk = {
        "chunk_id": "test-1",
        "text": "Test",
        "metadata": {"product_id": "p1", "category": "耳机", "brand": "Sony", "price": 99.0},
    }
    assert "product_id" in chunk["metadata"]
    assert "category" in chunk["metadata"]

def test_merge_chunks_no_duplicates():
    """Simple dedup test"""
    chunks = [
        {"chunk_id": "a", "text": "first"},
        {"chunk_id": "b", "text": "second"},
        {"chunk_id": "c", "text": "third"},
    ]
    seen = set()
    merged = []
    for c in chunks:
        if c["chunk_id"] not in seen:
            seen.add(c["chunk_id"])
            merged.append(c)
    assert len(merged) == 3

def test_merge_chunks_with_duplicates():
    chunks = [
        {"chunk_id": "a", "text": "first"},
        {"chunk_id": "a", "text": "first"},
        {"chunk_id": "b", "text": "second"},
    ]
    seen = set()
    merged = []
    for c in chunks:
        if c["chunk_id"] not in seen:
            seen.add(c["chunk_id"])
            merged.append(c)
    assert len(merged) == 2


def test_category_aliases_expand_common_user_terms():
    from app.services.retriever import _category_match_values

    assert "运动鞋" in _category_match_values("鞋")
    assert "运动鞋" in _category_match_values("鞋子")
    assert "T恤" in _category_match_values("衣服")
    assert "蓝牙耳机" in _category_match_values("耳机")
    assert "肉干肉脯" in _category_match_values("零食")
    assert "智能手表" in _category_match_values("手表")


def test_strip_food_noise_from_digital_query():
    from app.services.agent import _strip_cross_category_noise

    cleaned = _strip_cross_category_noise("好吃又便宜的华为手表", {"category": "手表"})

    assert "好吃" not in cleaned
    assert "华为手表" in cleaned


@pytest.mark.asyncio
async def test_strict_category_does_not_fallback_without_category(monkeypatch):
    from app.services import rag

    calls = []

    async def fake_embed(_query):
        return [0.1, 0.2]

    async def fake_search(**kwargs):
        calls.append(kwargs.get("category"))
        return [], 1.0

    monkeypatch.setattr(rag, "embed_text", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search", fake_search)

    result = await rag.retrieve("推荐鞋子", category="鞋子", strict_category=True)

    assert result["chunks"] == []
    assert calls == ["鞋子"]


@pytest.mark.asyncio
async def test_non_strict_category_can_fallback_without_category(monkeypatch):
    from app.services import rag

    calls = []

    async def fake_embed(_query):
        return [0.1, 0.2]

    async def fake_search(**kwargs):
        calls.append(kwargs.get("category"))
        if kwargs.get("category") is None:
            return [{"payload": {"product_id": "p1"}}], 1.0
        return [], 1.0

    monkeypatch.setattr(rag, "embed_text", fake_embed)
    monkeypatch.setattr(rag, "hybrid_search", fake_search)

    result = await rag.retrieve("随便推荐", category="未知品类", strict_category=False)

    assert len(result["chunks"]) == 1
    assert calls == ["未知品类", None]
