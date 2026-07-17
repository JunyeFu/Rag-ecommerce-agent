"""
Product assembly - validation, diversification, and card formatting.

Extracted from agent.py.
"""
import logging

from app.services.slot_management import _scoped_exclude_brands

logger = logging.getLogger("agent")


# ── 检索结果校验 ────────────────────────────────────────

MIN_MATCH_SCORE = 0.25  # 最低匹配度阈值，低于此值的商品不推荐


def _validate_ranked_products(ranked: list) -> tuple[list, bool]:
    """校验排序后的商品列表，过滤无效数据。

    Returns:
        (valid_products, is_reliable): 有效商品列表 + 是否可靠（最佳匹配>阈值）
    """
    valid = []
    for r in ranked:
        # 必要字段检查
        if not r.get("title") or not r.get("product_id"):
            logger.warning("Skipping product with missing title or product_id: %s", r)
            continue
        # 价格合理性 (安全转换，兼容字符串型价格)
        try:
            price = float(r.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            logger.warning("Skipping product with invalid price: %s (¥%s)", r.get("title"), price)
            continue
        valid.append(r)

    if not valid:
        return [], False

    best_score = valid[0].get("match_score", 0)
    is_reliable = best_score >= MIN_MATCH_SCORE
    if not is_reliable:
        logger.warning("Best match score %.2f below threshold %.2f", best_score, MIN_MATCH_SCORE)

    return valid, is_reliable


def _diversify_scenario_products(ranked: list, max_total: int = 5) -> list:
    """场景化推荐品类多样性采样：保证每品类至少 1 款，按 match_score 降序。

    Args:
        ranked: 已按 match_score 降序排列的商品列表
        max_total: 最多返回的商品数量

    Returns:
        品类多样化后的商品列表
    """
    if len(ranked) <= max_total:
        return ranked

    picked = []
    seen_categories: set[str] = set()
    remaining = []

    for r in ranked:
        cat = (r.get("category") or "").strip()
        if cat and cat not in seen_categories:
            picked.append(r)
            seen_categories.add(cat)
            if len(picked) >= max_total:
                return picked
        else:
            remaining.append(r)

    for r in remaining:
        if len(picked) >= max_total:
            break
        picked.append(r)

    logger.info(
        "Scenario diversity: %d categories -> %d products (from %d total)",
        len(seen_categories), len(picked), len(ranked),
    )
    return picked


# ═══════════════════════════════════════════════════════
# 共享辅助函数 - 消除 node_generate / generate_response 重复
# ═══════════════════════════════════════════════════════

def _extract_raw_products(chunks: list, limit: int = 10) -> list[dict]:
    """从 PostgreSQL chunks 提取原始商品属性列表"""
    raw = []
    for chunk in chunks[:limit]:
        p = chunk["payload"]
        image_urls = p.get("image_urls") or []
        if not image_urls and p.get("image_url"):
            image_urls = [p["image_url"]]
        raw.append({
            "product_id": p.get("product_id", ""),
            "title": p.get("title"),
            "price": p.get("price"),
            "rating": p.get("rating"),
            "brand": p.get("brand"),
            "category": p.get("category"),
            "attributes": p.get("attributes", {}),
            "semantic_score": round(chunk.get("final_score", chunk.get("score", 0.5)), 4),
            "highlights": p.get("highlights", []),
            "image_url": image_urls[0] if image_urls else None,
            "image_urls": image_urls,
        })
    return raw


def _build_user_prefs(slots: dict) -> dict:
    """从 slots 构造用户偏好字典"""
    return {
        "price_min": slots.get("price_min"),
        "price_max": slots.get("price_max"),
        "brand_preference": slots.get("brand_preference"),
        "attributes": slots.get("attributes", {}),
        "exclude_brands": _scoped_exclude_brands(slots),
        "exclude_attributes": slots.get("exclude_attributes", {}),
    }


def _assemble_cards(valid_ranked: list) -> list[dict]:
    """将排序校验后的商品列表组装为最终卡片格式"""
    cards = []
    for r in valid_ranked:
        cards.append({
            "product_id": r.get("product_id") or r.get("id") or "",
            "title": r["title"],
            "price": r.get("price"),
            "category": r.get("category", ""),
            "brand": r.get("brand"),
            "rating": r.get("rating"),
            "image_url": r.get("image_url") or (r.get("image_urls", [None]) or [None])[0],
            "image_urls": r.get("image_urls", []) if r.get("image_urls") else ([r.get("image_url")] if r.get("image_url") else []),
            "highlights": r.get("highlights", []),
            "match_score": r.get("match_score", 0.5),
            "rank_reason": r.get("rank_reason", ""),
            "scenarios": r.get("scenarios", []),
        })
    return cards


def _shorten_product_name(title: str, max_len: int = 28) -> str:
    """截短产品名称以提高对比文本可读性"""
    if len(title) <= max_len:
        return title
    # 尝试在括号/逗号处截断
    for sep in ("（", "(", "，", ","):
        pos = title.find(sep)
        if 6 < pos < max_len:
            return title[:pos]
    return title[:max_len-1] + "…"
