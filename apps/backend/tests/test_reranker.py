import pytest
pytestmark = pytest.mark.integration

"""Reranker 单元测试"""
import pytest
from app.services.reranker import rerank


@pytest.fixture
def sample_docs():
    return [
        {"content": "Sony WH-1000XM5 降噪耳机 蓝牙5.2 续航30小时", "score": 0.85, "metadata": {"id": "B001"}},
        {"content": "Apple AirPods Pro 主动降噪 空间音频 H2芯片", "score": 0.82, "metadata": {"id": "B002"}},
        {"content": "小米手环8 血氧监测 睡眠追踪 AMOLED屏", "score": 0.78, "metadata": {"id": "B003"}},
        {"content": "Bose QC45 降噪耳机 24小时续航 舒适佩戴", "score": 0.80, "metadata": {"id": "B004"}},
        {"content": "JBL Flip6 蓝牙音箱 IP67防水 12小时续航", "score": 0.75, "metadata": {"id": "B005"}},
    ]


def test_rerank_returns_top_k(sample_docs):
    result = rerank("降噪耳机推荐", sample_docs, top_k=3)
    assert len(result) == 3


def test_rerank_headphones_rank_above_speaker(sample_docs):
    """降噪相关商品（B001/B004/B002）应排在音箱（B005）前面"""
    result = rerank("降噪耳机推荐", sample_docs, top_k=5)
    headphone_ids = {"B001", "B004", "B002"}
    top3_ids = {r["metadata"]["id"] for r in result[:3]}
    assert len(top3_ids & headphone_ids) >= 2, f"Top3 should be headphones, got {top3_ids}"


def test_rerank_adds_scores(sample_docs):
    result = rerank("降噪耳机", sample_docs, top_k=3)
    for doc in result:
        assert "rerank_score" in doc, f"Missing rerank_score in {doc}"
        assert "final_score" in doc, f"Missing final_score in {doc}"
        assert 0 <= doc["final_score"] <= 1, f"final_score={doc['final_score']} out of [0,1]"


def test_empty_input():
    assert rerank("test", [], top_k=5) == []


def test_single_document():
    docs = [{"content": "Sony 耳机", "score": 0.9, "metadata": {"id": "B001"}}]
    result = rerank("耳机", docs, top_k=5)
    assert len(result) == 1
    assert result[0]["metadata"]["id"] == "B001"
