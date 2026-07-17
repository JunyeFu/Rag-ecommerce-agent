"""
Retrieval node - RAG retrieval with reranking and category filtering.

Extracted from agent.py.
"""
import logging

from app.services.agent_state import AgentState
from app.services.rag import retrieve as rag_retrieve
from app.services.reranker import rerank_async
from app.core.config import settings
from app.services.scenario import _map_scenario_to_categories, _pre_diversify_by_category
from app.services.slot_management import (
    _filter_chunks_by_requested_category,
    _filter_chunks_by_exclusions,
    _scoped_exclude_brands,
)

logger = logging.getLogger("agent")


async def node_retrieve(state: AgentState) -> AgentState:
    """RAG 检索"""
    if state["intent"] == "chitchat":
        state["retrieved_chunks"] = []
        return state

    query = state.get("rewritten_query") or state["query"]
    slots = state.get("slots", {})

    # 场景化购物：映射为已存在品类 -> 分别检索 -> 品类感知预采样 -> 合并
    if state.get("intent") == "scenario_shopping":
        scenario = slots.get("scenario", query)
        sub_queries = await _map_scenario_to_categories(query, scenario)
        logger.info("Scenario shopping: sub_queries=%s", sub_queries)
        state["_scenario_sub_queries"] = sub_queries  # 暂存供 generate_response 用

        all_chunks = []
        seen_ids = set()
        total_latency = 0.0
        for sq in sub_queries:
            result = await rag_retrieve(
                query=sq,
                top_k=settings.RETRIEVAL_TOP_K,  # 扩容候选池供品类多样性采样
                category=None,
                price_min=slots.get("price_min"),
                price_max=slots.get("price_max"),
            )
            total_latency += result["latency_ms"]
            for chunk in result["chunks"]:
                pid = chunk.get("payload", {}).get("product_id") or chunk.get("id")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_chunks.append(chunk)

        # 品类感知预采样：按品类分组取 top-3，交替合并（先于 reranker 全局排序）
        if all_chunks:
            all_chunks = _pre_diversify_by_category(all_chunks, max_per_category=3)
        state["retrieved_chunks"] = all_chunks
        state["latency_ms"] = total_latency
    else:
        result = await rag_retrieve(
            query=query,
            top_k=settings.RETRIEVAL_TOP_K,
            category=slots.get("category"),
            price_min=slots.get("price_min"),
            price_max=slots.get("price_max"),
            exclude_brands=_scoped_exclude_brands(slots),
            exclude_categories=slots.get("exclude_categories"),
            exclude_attributes=slots.get("exclude_attributes"),
            strict_category=bool(slots.get("category")),
        )

        state["retrieved_chunks"] = result["chunks"]
        state["latency_ms"] = result["latency_ms"]

    if slots.get("category") and state["retrieved_chunks"]:
        state["retrieved_chunks"] = _filter_chunks_by_requested_category(
            state["retrieved_chunks"], slots.get("category")
        )
    state["retrieved_chunks"] = _filter_chunks_by_exclusions(state.get("retrieved_chunks", []), slots)

    # 文本级兜底过滤：排除 title/highlights 中含否定词的商品
    excluded_brand_terms = {str(b).strip().lower() for b in _scoped_exclude_brands(slots)}
    text_terms = [
        t for t in (slots.get("exclude_text_terms", []) or [])
        if str(t).strip().lower() not in excluded_brand_terms
    ]
    if text_terms and state["retrieved_chunks"]:
        filtered = []
        for chunk in state["retrieved_chunks"]:
            p = chunk.get("payload", {})
            haystack = (p.get("title", "") + " " + " ".join(p.get("highlights", []))).lower()
            if not any(t.lower() in haystack for t in text_terms):
                filtered.append(chunk)
        dropped = len(state["retrieved_chunks"]) - len(filtered)
        if dropped > 0:
            logger.info("Text filter: dropped %d chunks containing %s", dropped, text_terms)
        state["retrieved_chunks"] = filtered

    # ── Precision@K 监控 ──
    chunks_before_rerank = len(state["retrieved_chunks"])
    if state["retrieved_chunks"]:
        scores = []
        categories_seen = set()
        for c in state["retrieved_chunks"][:10]:
            p = c.get("payload", {})
            s = c.get("score") or p.get("score", 0)
            scores.append(round(float(s), 3))
            cat = p.get("category", "")
            if cat:
                categories_seen.add(cat)
        logger.info("Retrieval quality: n=%d top_score=%.3f avg_score=%.3f categories=%d",
                    chunks_before_rerank,
                    max(scores) if scores else 0,
                    sum(scores) / len(scores) if scores else 0,
                    len(categories_seen))

    # ── Reranker 精排（lifespan 已预加载模型，不再阻塞首请求） ──
    # 场景化购物已通过 _pre_diversify_by_category 做品类感知预采样，跳过全局 rerank 避免
    # 语义强势品类垄断 top 位，保持跨品类多样性。
    if state["retrieved_chunks"] and state.get("intent") != "chitchat" and state.get("intent") != "scenario_shopping":
        try:
            query_text = state.get("rewritten_query") or state["query"]
            n_before = len(state["retrieved_chunks"])
            state["retrieved_chunks"] = await rerank_async(
                query_text, state["retrieved_chunks"], top_k=settings.RERANKER_TOP_K
            )
            logger.info("Reranker applied: %d -> %d chunks re-ranked", n_before, len(state["retrieved_chunks"]))
        except Exception as e:
            logger.warning("Reranker unavailable, using raw retrieval: %s", e)

    logger.info("Agent retrieved %d chunks in %.0fms", len(state["retrieved_chunks"]), state["latency_ms"])
    return state
