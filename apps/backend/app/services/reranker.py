"""
重排序 - Sentence-Transformers Cross-Encoder

对向量检索粗排结果做精排，提升 Top-K 相关性。
接口: (query, list[doc]) -> list[ranked_doc]

兼容两种文档格式:
- PostgreSQL: {"id":"...", "score":0.8, "payload":{"text":"...", ...}}
- 通用: {"content":"...", "score":0.8, "metadata":{...}}
"""
import asyncio
import logging
import threading
import time
from typing import List, Dict, Optional

logger = logging.getLogger("reranker")

_RETRY_COOLDOWN_SECONDS = 300

_reranker_model = None
_model_lock = threading.Lock()
_failure_time: float = 0.0


def _get_content(doc: Dict) -> str:
    """从 PostgreSQL 或通用格式文档中提取文本内容"""
    payload = doc.get("payload", {})
    if isinstance(payload, dict):
        parts = []
        if payload.get("title"):
            parts.append(payload["title"])
        if payload.get("category"):
            parts.append(payload["category"])
        if payload.get("brand"):
            parts.append(payload["brand"])
        if payload.get("highlights"):
            parts.extend(payload["highlights"][:5])
        if payload.get("description"):
            parts.append(str(payload["description"])[:200])
        if payload.get("attributes"):
            parts.append(" ".join(str(v) for v in payload["attributes"].values()))
        if parts:
            return " ".join(parts)
        if payload.get("text"):
            return payload["text"]
    return doc.get("content", "") or str(payload) if payload else ""


def _get_model():
    """加载 BGE-Reranker v2-m3 CrossEncoder（线程安全 + 冷却重试）

    失败后进入冷却期 (_RETRY_COOLDOWN_SECONDS)，冷却期内跳过重试，
    冷却期满后允许重新加载（应对瞬时故障如 OOM / I/O 错误）。
    """
    global _reranker_model, _failure_time

    if _reranker_model is not None:
        return _reranker_model if _reranker_model is not False else None

    if _reranker_model is False and _failure_time > 0:
        elapsed = time.monotonic() - _failure_time
        if elapsed < _RETRY_COOLDOWN_SECONDS:
            return None
        logger.info("Reranker cooldown expired (%.0fs), retrying load", elapsed)
        _reranker_model = None

    with _model_lock:
        if _reranker_model is not None:
            return _reranker_model if _reranker_model is not False else None

        if _reranker_model is False and _failure_time > 0:
            elapsed = time.monotonic() - _failure_time
            if elapsed < _RETRY_COOLDOWN_SECONDS:
                return None
            logger.info("Reranker cooldown expired (%.0fs), retrying load", elapsed)
            _reranker_model = None

        from sentence_transformers import CrossEncoder
        from app.core.config import settings

        model_name = settings.RERANKER_MODEL
        logger.info("Loading reranker model: %s", model_name)
        try:
            _reranker_model = CrossEncoder(model_name, device="cpu")
            _failure_time = 0.0
            logger.info("Reranker model loaded (CPU)")
        except Exception as e:
            logger.warning("Reranker unavailable: %s", e)
            _reranker_model = False
            _failure_time = time.monotonic()
    return _reranker_model if _reranker_model is not False else None


def rerank(
    query: str,
    documents: List[Dict],
    top_k: int = 10
) -> List[Dict]:
    """
    对检索结果重排序。

    Args:
        query: 用户查询
        documents: [{"content": "...", "score": 0.8, "metadata": {...}}, ...]
        top_k: 返回 Top-K

    Returns:
        按 relevance 降序排列的文档列表，新增 rerank_score 和 final_score 字段
    """
    if not documents:
        return []

    model = _get_model()

    if model is None:
        logger.warning("Reranker model unavailable, falling back to original scores")
        ranked = [{**doc, "rerank_score": doc.get("score", 0.5),
                   "final_score": doc.get("score", 0.5)} for doc in documents]
        ranked.sort(key=lambda x: x["final_score"], reverse=True)
        return ranked[:top_k]

    pairs = [(query, _get_content(doc)) for doc in documents]

    scores = model.predict(pairs)

    if not hasattr(scores, '__iter__'):
        scores = [float(scores)]
    else:
        scores = [float(s) for s in scores]

    def _sigmoid(x):
        import math
        try:
            return 1.0 / (1.0 + math.exp(-x))
        except OverflowError:
            return 1.0 if x > 0 else 0.0

    ranked = []
    for doc, score in zip(documents, scores):
        normalized_score = _sigmoid(score)
        entry = {**doc}
        entry["rerank_score"] = round(normalized_score, 4)
        entry["final_score"] = round(
            float(doc.get("score", 0.0)) * 0.3 + normalized_score * 0.7,
            4
        )
        ranked.append(entry)

    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    result = ranked[:top_k]
    logger.info("Rerank: '%s' -> %d docs reranked, top_k=%d",
                query[:50], len(documents), len(result))
    return result


async def rerank_async(
    query: str,
    documents: List[Dict],
    top_k: int = 10
) -> List[Dict]:
    """异步包装 - 在线程池中执行 CrossEncoder 推理，不阻塞事件循环"""
    return await asyncio.to_thread(rerank, query, documents, top_k)
