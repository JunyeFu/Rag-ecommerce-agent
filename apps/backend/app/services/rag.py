"""
RAG 检索入口 — 编排 retrieval pipeline
"""
import time
import logging
from app.services.retriever import hybrid_search
from app.services.embedding import embed_text

logger = logging.getLogger("rag")


async def retrieve(
    query: str,
    top_k: int = 10,
    category: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    exclude_brands: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    exclude_attributes: dict[str, str] | None = None,
    strict_category: bool = False,
    use_hybrid: bool = True,
) -> dict:
    """
    RAG 检索主入口:
    1. query → embedding
    2. 向量 + 元数据混合检索（含否定排除）
    3. 返回 {'chunks': [...], 'latency_ms': float}
    """
    t0 = time.monotonic()

    vector = await embed_text(query)
    chunks, search_ms = await hybrid_search(
        query_vector=vector,
        query_text=query,
        category=category,
        price_min=price_min,
        price_max=price_max,
        exclude_brands=exclude_brands,
        exclude_categories=exclude_categories,
        exclude_attributes=exclude_attributes,
        top_k=top_k,
        use_hybrid=use_hybrid,
    )

    # 品类+价格 组合过滤无结果 → 分级回退
    if not chunks and category:
        # 策略A: 先尝试只保留品类，放宽价格（保留上下文）
        if price_min is not None or price_max is not None:
            logger.info("RAG: category='%s' + price range returned 0, retry category-only", category)
            chunks, search_ms = await hybrid_search(
                query_vector=vector, query_text=query,
                category=category, price_min=None, price_max=None,
                exclude_brands=exclude_brands, exclude_categories=exclude_categories,
                exclude_attributes=exclude_attributes, top_k=top_k,
                use_hybrid=use_hybrid,
            )

    if not chunks and category:
        # 策略B: 非严格模式才允许丢弃品类过滤；严格模式避免跨品类乱推荐。
        if strict_category:
            logger.warning("RAG: category='%s' returned 0 with strict_category=True, keep empty result", category)
        else:
            logger.info("RAG: category='%s' returned 0, retry without category (strict_category=False)", category)
            chunks, search_ms = await hybrid_search(
                query_vector=vector, query_text=query,
                category=None,
                price_min=price_min, price_max=price_max,
                exclude_brands=exclude_brands, exclude_categories=exclude_categories,
                exclude_attributes=exclude_attributes, top_k=top_k,
                use_hybrid=use_hybrid,
            )

    total_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "RAG retrieve: '%s' → %d chunks (embed+search=%.0fms)",
        query[:60], len(chunks), total_ms,
    )

    return {
        "chunks": chunks,
        "latency_ms": round(total_ms, 1),
        "query": query,
    }
