"""
混合检索 - pgvector 向量检索 + tsvector 全文搜索 + RRF 融合
"""
import time
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.services.embedding import embed_text

logger = logging.getLogger("retriever")


_CATEGORY_ALIASES: dict[str, list[str]] = {
    "鞋": ["鞋", "鞋子", "运动鞋", "休闲鞋", "跑鞋", "篮球鞋", "帆布鞋", "板鞋", "皮鞋", "老爹鞋"],
    "鞋子": ["鞋子", "运动鞋", "休闲鞋", "跑鞋", "篮球鞋", "帆布鞋", "板鞋", "皮鞋", "老爹鞋"],
    "衣服": ["衣服", "服装", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"],
    "服装": ["服装", "衣服", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"],
    "衣物": ["衣物", "衣服", "服装", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"],
    "耳机": ["耳机", "蓝牙耳机", "降噪耳机", "无线耳机", "头戴式耳机", "入耳式耳机", "运动耳机"],
    "蓝牙耳机": ["蓝牙耳机", "耳机", "无线耳机", "入耳式耳机", "运动耳机"],
    "图书": ["图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"],
    "书": ["图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"],
    "书籍": ["图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"],
    "零食": ["零食", "食品", "休闲零食", "肉干肉脯", "坚果炒货", "饼干糕点", "糖果巧克力"],
    "食品": ["食品", "零食", "休闲零食", "肉干肉脯", "坚果炒货", "饼干糕点", "糖果巧克力"],
    "手机": ["手机", "智能手机"],
    "手表": ["手表", "智能手表", "运动手表"],
    "智能手表": ["智能手表", "手表", "运动手表"],
}


def _category_match_values(category: str | None) -> list[str]:
    if not category:
        return []
    cleaned = category.strip()
    values = _CATEGORY_ALIASES.get(cleaned, [cleaned])
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _row_to_payload(row) -> dict:
    """将 SQLAlchemy Row 转为检索结果 payload 格式"""
    image_urls = list(row.image_urls or [])
    image_url = image_urls[0] if image_urls else None
    return {
        "product_id": str(row.source_product_id or row.id),
        "title": row.title or "",
        "category": row.category or "",
        "brand": row.brand or "",
        "price": float(row.price or 0),
        "rating": float(row.rating or 0),
        "rating_count": 0,
        "highlights": list(row.highlights or []),
        "scenarios": list(row.scenarios or []),
        "attributes": dict(row.attributes or {}),
        "image_url": image_url,
        "image_urls": image_urls,
    }


def _build_where_clause(
    category: str | None,
    price_min: float | None,
    price_max: float | None,
    exclude_brands: list[str] | None,
    exclude_categories: list[str] | None,
    exclude_attributes: dict[str, str] | None,
) -> tuple[str, dict]:
    """构建 SQL WHERE 子句和参数"""
    clauses = ["embedding IS NOT NULL"]
    params: dict = {}

    if category:
        cat_values = _category_match_values(category)
        if len(cat_values) == 1:
            clauses.append("category = :category")
            params["category"] = cat_values[0]
        else:
            clauses.append("category = ANY(:categories)")
            params["categories"] = cat_values

    if price_min is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = price_min
    if price_max is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = price_max

    if exclude_brands:
        clauses.append("NOT (brand = ANY(:exclude_brands))")
        params["exclude_brands"] = exclude_brands

    if exclude_categories:
        clauses.append("NOT (category = ANY(:exclude_categories))")
        params["exclude_categories"] = exclude_categories

    if exclude_attributes:
        for i, (attr_key, attr_val) in enumerate(exclude_attributes.items()):
            key_param = f"excl_attr_key_{i}"
            val_param = f"excl_attr_val_{i}"
            clauses.append(f"NOT (attributes->>:{key_param} = :{val_param})")
            params[key_param] = attr_key
            params[val_param] = attr_val

    return " AND ".join(clauses), params


def _rrf_fuse(
    dense_results: list[dict],
    keyword_results: list[dict],
    top_k: int,
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion: 合并向量检索和关键词检索结果"""
    scores: dict[str, float] = {}
    all_items: dict[str, dict] = {}

    for rank, item in enumerate(dense_results):
        pid = item["payload"].get("product_id") or item["id"]
        scores[pid] = scores.get(pid, 0) + 1.0 / (k + rank + 1)
        all_items[pid] = item

    for rank, item in enumerate(keyword_results):
        pid = item["payload"].get("product_id") or item["id"]
        scores[pid] = scores.get(pid, 0) + 1.0 / (k + rank + 1)
        all_items[pid] = item

    sorted_pids = sorted(scores.keys(), key=lambda p: scores[p], reverse=True)
    result = []
    for pid in sorted_pids[:top_k]:
        item = all_items[pid].copy()
        item["score"] = scores[pid]
        result.append(item)
    return result


async def _search_knowledge_chunks(
    db: AsyncSession,
    vector: list[float],
    top_k: int,
) -> list[dict]:
    """向量检索 knowledge_chunks 表，返回带 source_type=knowledge 标记的结果"""
    try:
        sql = text("""
            SELECT id, doc_id, chunk_text, metadata,
                   1 - (embedding <=> :vector::vector) AS score
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :vector::vector
            LIMIT :top_k
        """)
        result = await db.execute(sql, {"vector": str(vector), "top_k": top_k})
        rows = result.fetchall()
    except Exception as e:
        logger.warning("knowledge_chunks search skipped (table may not exist yet): %s", e)
        return []

    items: list[dict] = []
    for row in rows:
        items.append({
            "id": str(row.id),
            "score": float(row.score or 0),
            "payload": {
                "text": row.chunk_text or "",
                "source_type": "knowledge",
                "doc_id": row.doc_id or "",
                "metadata": dict(row.metadata or {}),
            },
        })
    return items


async def hybrid_search(
    query_vector: list[float],
    query_text: str = "",
    category: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    exclude_brands: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    exclude_attributes: dict[str, str] | None = None,
    top_k: int = 10,
    use_hybrid: bool = True,
) -> tuple[list[dict], float]:
    """
    混合检索:
    1. 向量语义检索 (dense) - pgvector <=> cosine distance
    2. 关键词检索 (keyword) - tsvector @@ plainto_tsquery
    3. RRF 融合两路结果
    4. 元数据过滤 (category / price range / 否定排除)
    返回: (结果列表, 检索耗时ms)
    """
    t0 = time.monotonic()

    if AsyncSessionLocal is None:
        logger.warning("Database not configured, returning empty results")
        return [], 0.0

    where_clause, params = _build_where_clause(
        category, price_min, price_max,
        exclude_brands, exclude_categories, exclude_attributes,
    )

    vector_param = str(query_vector)

    try:
        async with AsyncSessionLocal() as db:
            dense_sql = text(f"""
                SELECT id, title, description, price, category, brand, rating,
                       highlights, scenarios, attributes, image_urls, source_product_id,
                       1 - (embedding <=> :vector::vector) AS score
                FROM products
                WHERE {where_clause}
                ORDER BY embedding <=> :vector::vector
                LIMIT :top_k
            """)
            params["vector"] = vector_param
            params["top_k"] = top_k
            dense_result = await db.execute(dense_sql, params)
            dense_rows = dense_result.fetchall()

            if use_hybrid and query_text:
                kw_params = dict(params)
                kw_sql = text(f"""
                    SELECT id, title, description, price, category, brand, rating,
                           highlights, scenarios, attributes, image_urls, source_product_id,
                           ts_rank(search_vector, plainto_tsquery(:query_text)) AS score
                    FROM products
                    WHERE {where_clause}
                      AND search_vector @@ plainto_tsquery(:query_text)
                    ORDER BY score DESC
                    LIMIT :top_k
                """)
                kw_params["query_text"] = query_text
                kw_result = await db.execute(kw_sql, kw_params)
                kw_rows = kw_result.fetchall()
            else:
                kw_rows = []

            knowledge_rows = await _search_knowledge_chunks(db, query_vector, top_k * 2)
    except Exception as e:
        logger.error("hybrid_search DB error: %s", e)
        return [], 0.0

    dense_items = []
    for row in dense_rows:
        dense_items.append({"id": str(row.id), "score": float(row.score or 0), "payload": _row_to_payload(row)})

    keyword_items = []
    for row in kw_rows:
        keyword_items.append({"id": str(row.id), "score": float(row.score or 0), "payload": _row_to_payload(row)})

    if knowledge_rows:
        fusion_dense = dense_items + knowledge_rows
        items = _rrf_fuse(fusion_dense, keyword_items, top_k)
    elif use_hybrid and keyword_items:
        items = _rrf_fuse(dense_items, keyword_items, top_k)
    else:
        items = dense_items

    elapsed_ms = (time.monotonic() - t0) * 1000

    logger.info(
        "Retrieve: query='%s' -> %d results (dense=%d, kw=%d, knowledge=%d) in %.0fms (category=%s, price=%s-%s, exclude_br=%s)",
        query_text[:50], len(items), len(dense_items), len(keyword_items), len(knowledge_rows), elapsed_ms,
        category or "*", price_min or "*", price_max or "*",
        exclude_brands or [],
    )

    return items, elapsed_ms


async def search_similar_products(
    query_text: str,
    top_k: int = 8,
) -> list[dict]:
    """
    拍照找货专用：文本查询 -> Embedding -> pgvector 向量检索 -> 结构化商品列表

    Args:
        query_text: 由视觉解析提取的商品描述文本
        top_k: 返回数量

    Returns:
        [{"product_id":..., "title":..., "price":..., "rating":...,
          "match_score":..., "highlights":..., "image_url":...}, ...]
    """
    query_vector = await embed_text(query_text)

    if AsyncSessionLocal is None:
        logger.warning("Database not configured, returning empty results")
        return []

    vector_param = str(query_vector)

    try:
        async with AsyncSessionLocal() as db:
            sql = text("""
                SELECT id, title, price, rating, brand, category,
                       highlights, image_urls, source_product_id,
                       1 - (embedding <=> :vector::vector) AS score
                FROM products
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :vector::vector
                LIMIT :top_k
            """)
            result = await db.execute(sql, {"vector": vector_param, "top_k": top_k})
            rows = result.fetchall()
    except Exception as e:
        logger.error("search_similar_products DB error: %s", e)
        return []

    products = []
    for row in rows:
        image_urls = list(row.image_urls or [])
        products.append({
            "product_id": str(row.source_product_id or row.id),
            "title": row.title or "",
            "price": float(row.price or 0),
            "rating": float(row.rating or 0),
            "brand": row.brand or "",
            "category": row.category or "",
            "match_score": round(float(row.score or 0), 4),
            "score": round(float(row.score or 0), 4),
            "highlights": list(row.highlights or [])[:3],
            "image_url": image_urls[0] if image_urls else None,
            "image_urls": image_urls,
        })

    logger.info("Similar search: '%s' -> %d products", query_text[:60], len(products))
    return products
