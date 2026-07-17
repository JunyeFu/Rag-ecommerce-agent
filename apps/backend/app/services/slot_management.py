"""
Slot management - category hints, slot state, filtering, and exclusion helpers.

Extracted from agent.py. Contains all category constants, category hint functions,
category context functions, slot state functions, product/chunk merge functions,
filter functions, and exclusion helpers.
"""
import re
import logging

from app.services.exclusion_rules import (
    expand_exclude_brands,
    normalize_exclusion_slots,
    product_violates_exclusions,
)
from app.services.rag import retrieve as rag_retrieve
from app.services.agent_state import _SLOT_KEYS

logger = logging.getLogger("agent")


# ── Category constants ──

_DIGITAL_CATEGORIES = {
    "手机", "智能手机", "手表", "智能手表", "耳机", "蓝牙耳机", "平板", "平板电脑",
    "电脑", "笔记本", "相机", "音箱", "键盘", "鼠标",
}
_CATEGORY_PREF_KEYS = ("price_min", "price_max", "brand_preference", "attributes", "scenario")
_FOOD_ONLY_TERMS = {"好吃", "美味", "口味", "味道", "香", "不难吃", "难吃", "甜", "辣", "咸"}
_FOOD_CATEGORY_TERMS = _FOOD_ONLY_TERMS | {
    "零食", "食品", "吃的", "小吃", "便宜好吃", "好吃便宜", "下饭", "饱腹", "健康",
    "坚果", "肉脯", "肉干", "饼干", "薯片", "糖果", "辣条", "果干", "泡面", "面包",
}
_DIGITAL_QUERY_TERMS = _DIGITAL_CATEGORIES | {
    "华为", "苹果", "小米", "荣耀", "oppo", "vivo", "oneplus", "iphone", "ipad",
    "拍照", "续航", "屏幕", "充电", "降噪", "蓝牙", "运动", "通话", "5g", "cpu",
}
_EXPLICIT_CATEGORY_HINTS = (
    ("智能手表", "手表"),
    ("蓝牙耳机", "耳机"),
    ("智能手机", "手机"),
    ("运动鞋", "鞋"),
    ("休闲鞋", "鞋"),
    ("篮球鞋", "鞋"),
    ("帆布鞋", "鞋"),
    ("老爹鞋", "鞋"),
    ("跑鞋", "鞋"),
    ("皮鞋", "鞋"),
    ("板鞋", "鞋"),
    ("鞋子", "鞋"),
    ("衣服", "衣服"),
    ("服装", "衣服"),
    ("衣物", "衣服"),
    ("女装", "衣服"),
    ("男装", "衣服"),
    ("夏装", "衣服"),
    ("T恤", "衣服"),
    ("t恤", "衣服"),
    ("衬衫", "衣服"),
    ("卫衣", "衣服"),
    ("外套", "衣服"),
    ("夹克", "衣服"),
    ("羽绒服", "衣服"),
    ("连衣裙", "衣服"),
    ("裙子", "衣服"),
    ("裤子", "衣服"),
    ("零食", "零食"),
    ("食品", "零食"),
    ("小吃", "零食"),
    ("耳机", "耳机"),
    ("手表", "手表"),
    ("手机", "手机"),
    ("平板", "平板"),
    ("图书", "图书"),
    ("书籍", "图书"),
    ("鞋", "鞋"),
)


# ── Category hint functions ──

def _apply_query_category_hint(slots: dict, query: str) -> None:
    if not isinstance(slots, dict) or slots.get("category"):
        return

    inferred = _infer_explicit_category_from_text(query) or _infer_category_from_query(query)
    if inferred:
        slots["category"] = inferred


def _apply_history_category_hint(slots: dict, history: list[dict] | None) -> None:
    if not isinstance(slots, dict) or slots.get("category"):
        return

    for message in reversed(history or []):
        if message.get("role") != "user":
            continue
        content = message.get("content") or ""
        inferred = _infer_explicit_category_from_text(content) or _infer_category_from_query(content)
        if inferred:
            slots["category"] = inferred
            return


def _infer_explicit_category_from_text(text: str) -> str | None:
    normalized = re.sub(r"\s+", "", (text or "").lower())
    if not normalized:
        return None
    for term, category in _EXPLICIT_CATEGORY_HINTS:
        if term.lower() in normalized:
            return category
    return None


def _infer_category_from_query(query: str) -> str | None:
    normalized = re.sub(r"\s+", "", (query or "").lower())
    if not normalized:
        return None
    if any(term in normalized for term in _FOOD_CATEGORY_TERMS) and not any(
        term in normalized for term in _DIGITAL_QUERY_TERMS
    ):
        return "零食"
    return None


def _strip_cross_category_noise(text: str, slots: dict) -> str:
    """Remove food-only adjectives from digital product queries such as "好吃的华为手表"."""
    category = str((slots or {}).get("category") or "").strip()
    if category not in _DIGITAL_CATEGORIES:
        return text
    cleaned = text
    for term in _FOOD_ONLY_TERMS:
        cleaned = cleaned.replace(term, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or text


def _sanitize_slots_for_category(slots: dict) -> None:
    category = str((slots or {}).get("category") or "").strip()
    if category not in _DIGITAL_CATEGORIES:
        return
    attrs = slots.get("attributes")
    if isinstance(attrs, dict):
        for key in list(attrs.keys()):
            joined = f"{key}{attrs.get(key)}"
            if any(term in joined for term in _FOOD_ONLY_TERMS):
                attrs.pop(key, None)
    for key in ("exclude_text_terms",):
        terms = slots.get(key)
        if isinstance(terms, list):
            slots[key] = [term for term in terms if not any(food in str(term) for food in _FOOD_ONLY_TERMS)]


# ── Category context functions ──

def _categories_equivalent(left: str | None, right: str | None) -> bool:
    left = (left or "").strip()
    right = (right or "").strip()
    if not left or not right:
        return False
    return left == right or _category_matches_request(left, right) or _category_matches_request(right, left)


def _has_category_change(prev_slots: dict, new_slots: dict) -> bool:
    prev_category = (prev_slots or {}).get("category")
    new_category = (new_slots or {}).get("category")
    return bool(prev_category and new_category and not _categories_equivalent(prev_category, new_category))


def _prune_previous_slots_for_category_change(prev_slots: dict, new_slots: dict) -> dict:
    """Drop category-specific history when the user switches to a different product category."""
    if not prev_slots:
        return {}

    prev_category = prev_slots.get("category")
    new_category = (new_slots or {}).get("category")
    if not prev_category or not new_category or _categories_equivalent(prev_category, new_category):
        return dict(prev_slots)

    pruned = dict(prev_slots)
    for key in (
        "category",
        "brand_preference",
        "attributes",
        "scenario",
        "missing_slots",
        "exclude_brands",
        "exclude_attributes",
        "exclude_text_terms",
    ):
        pruned.pop(key, None)
    logger.info("Category changed %s -> %s, pruned category-scoped preferences", prev_category, new_category)
    return pruned


def _current_category_from_context(context: dict | None) -> str | None:
    if not isinstance(context, dict):
        return None
    category = context.get("current_category") or context.get("category")
    category = str(category or "").strip()
    return category or None


def _update_category_context(context: dict | None, slots: dict | None) -> dict:
    """Maintain a per-conversation category preference map independent of result hits."""
    updated = dict(context or {})
    category = str((slots or {}).get("category") or "").strip()
    if not category:
        return updated

    updated["current_category"] = category
    pref_map = dict(updated.get("category_preferences") or {})
    category_pref = dict(pref_map.get(category) or {})
    for key in _CATEGORY_PREF_KEYS:
        value = (slots or {}).get(key)
        if value not in (None, {}, []):
            category_pref[key] = value
    pref_map[category] = category_pref
    updated["category_preferences"] = pref_map
    return updated


# ── Slot state functions ──

def _previous_slots_from_state(state: dict) -> dict:
    """Read slots from current nested state and legacy top-level session fields.

    Defensively strips keys that leaked from old session state nesting contamination
    (intent, product_cards, nested slots dict, etc.) so they don't pollute the new
    merged slots and cause cross-category exclusion leakage.
    """
    nested = state.get("slots")
    if isinstance(nested, dict):
        prev = dict(nested)
        # 清除因旧版 state->slots 嵌套导致的脏数据泄露
        for bad_key in ("intent", "product_cards", "slots", "latency_ms", "error",
                        "query", "session_id", "_clarify_done", "_comparison_dims",
                        "_is_reliable", "_query_was_expanded"):
            prev.pop(bad_key, None)
    else:
        prev = {}
    for key in _SLOT_KEYS:
        if key not in prev and state.get(key) is not None:
            prev[key] = state[key]
    context_category = _current_category_from_context(state.get("category_context"))
    if context_category:
        prev["category"] = context_category
    return prev


def _build_rewrite_base(query: str, expanded: str, slots: dict, has_negation: bool, negation: dict) -> str:
    if has_negation and slots.get("category"):
        return f"{slots['category']} 热门推荐 同类商品"
    positive_q = (negation or {}).get("positive_query", "") if has_negation else ""
    return _strip_cross_category_noise(positive_q or expanded or query, slots)


# ── Product/chunk merge functions ──

def _product_key_from_chunk(chunk: dict) -> str:
    payload = chunk.get("payload", {}) or {}
    return str(payload.get("product_id") or chunk.get("id") or payload.get("title") or "")


def _merge_product_chunks(primary: list[dict], supplements: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for chunk in (primary or []) + (supplements or []):
        key = _product_key_from_chunk(chunk)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(chunk)
    return merged


def _category_matches_request(product_category: str, requested_category: str) -> bool:
    if not requested_category:
        return True
    product_category = (product_category or "").strip()
    requested_category = requested_category.strip()
    if product_category == requested_category:
        return True
    aliases = {
        "平板": {"平板", "平板电脑"},
        "平板电脑": {"平板", "平板电脑"},
        "鞋": {"鞋", "鞋子", "运动鞋", "休闲鞋", "跑鞋", "篮球鞋", "帆布鞋", "板鞋", "皮鞋", "老爹鞋"},
        "鞋子": {"鞋子", "运动鞋", "休闲鞋", "跑鞋", "篮球鞋", "帆布鞋", "板鞋", "皮鞋", "老爹鞋"},
        "衣服": {"衣服", "服装", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"},
        "服装": {"服装", "衣服", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"},
        "衣物": {"衣物", "衣服", "服装", "T恤", "衬衫", "卫衣", "外套", "夹克", "羽绒服", "连衣裙", "裙装", "裤装", "牛仔裤", "运动服", "户外"},
        "耳机": {"耳机", "蓝牙耳机", "降噪耳机", "无线耳机", "头戴式耳机", "入耳式耳机", "运动耳机"},
        "蓝牙耳机": {"蓝牙耳机", "耳机", "无线耳机", "入耳式耳机", "运动耳机"},
        "图书": {"图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"},
        "书": {"图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"},
        "书籍": {"图书", "书籍", "教材", "小说", "童书", "绘本", "阅读"},
        "零食": {"零食", "食品", "休闲零食", "肉干肉脯", "坚果炒货", "饼干糕点", "糖果巧克力"},
        "食品": {"食品", "零食", "休闲零食", "肉干肉脯", "坚果炒货", "饼干糕点", "糖果巧克力"},
        "手机": {"手机", "智能手机"},
        "手表": {"手表", "智能手表", "运动手表"},
        "智能手表": {"智能手表", "手表", "运动手表"},
    }
    return product_category in aliases.get(requested_category, {requested_category})


def _needs_strict_category_guard(requested_category: str) -> bool:
    return (requested_category or "").strip() in {
        "平板", "平板电脑",
        "鞋", "鞋子",
        "衣服", "服装", "衣物",
        "耳机", "蓝牙耳机",
        "图书", "书", "书籍",
        "零食", "食品",
        "手机",
        "手表", "智能手表",
    }


# ── Filter functions ──

def _filter_chunks_by_requested_category(chunks: list[dict], requested_category: str) -> list[dict]:
    if not _needs_strict_category_guard(requested_category):
        return chunks or []
    filtered = [
        chunk for chunk in (chunks or [])
        if _category_matches_request((chunk.get("payload", {}) or {}).get("category", ""), requested_category)
    ]
    dropped = len(chunks or []) - len(filtered)
    if dropped:
        logger.info("Category guard: dropped %d non-%s candidates", dropped, requested_category)
    return filtered


def _filter_products_by_requested_category(products: list[dict], requested_category: str) -> list[dict]:
    if not _needs_strict_category_guard(requested_category):
        return products or []
    return [
        product for product in (products or [])
        if _category_matches_request(product.get("category", ""), requested_category)
    ]


def _filter_chunks_by_exclusions(chunks: list[dict], slots: dict) -> list[dict]:
    if not chunks:
        return []
    normalized = normalize_exclusion_slots(slots or {})
    filtered = [
        chunk for chunk in chunks
        if not product_violates_exclusions((chunk.get("payload", {}) or {}), normalized)
    ]
    dropped = len(chunks) - len(filtered)
    if dropped:
        logger.info("Hard exclusion filter: dropped %d chunks", dropped)
    return filtered


def _filter_products_by_exclusions(products: list[dict], slots: dict) -> list[dict]:
    if not products:
        return []
    normalized = normalize_exclusion_slots(slots or {})
    filtered = [p for p in products if not product_violates_exclusions(p, normalized)]
    dropped = len(products) - len(filtered)
    if dropped:
        logger.info("Hard exclusion filter: dropped %d products", dropped)
    return filtered


async def _retrieve_same_category_supplements(query: str, slots: dict, existing_chunks: list[dict]) -> list[dict]:
    """Expand the candidate pool inside the current category after exclusions."""
    category = slots.get("category")
    if not category:
        return existing_chunks or []

    result = await rag_retrieve(
        query=f"{category} 热门 推荐 {query}",
        top_k=30,
        category=category,
        price_min=slots.get("price_min"),
        price_max=slots.get("price_max"),
        exclude_brands=_scoped_exclude_brands(slots),
        exclude_categories=slots.get("exclude_categories"),
        exclude_attributes=slots.get("exclude_attributes"),
        strict_category=True,
    )
    merged = _merge_product_chunks(existing_chunks or [], result.get("chunks", []))
    merged = _filter_chunks_by_requested_category(merged, category)
    return _filter_chunks_by_exclusions(merged, slots)


# ── Exclusion helpers ──

# 品牌中英文别名映射 - 解决 PostgreSQL 中同一品牌中英文名不一致导致排除失效的问题
_BRAND_ALIASES: dict[str, str] = {
    "华为": "Huawei", "Huawei": "华为",
    "苹果": "Apple", "Apple": "苹果",
    "小米": "Xiaomi", "Xiaomi": "小米",
    "阿迪达斯": "Adidas", "Adidas": "阿迪达斯",
    "索尼": "Sony", "Sony": "索尼",
    "耐克": "Nike", "Nike": "耐克",
    "联想": "Lenovo", "Lenovo": "联想",
    "三星": "Samsung", "Samsung": "三星",
    "惠普": "HP", "HP": "惠普",
}


def _expand_brand_aliases(brands: list[str]) -> list[str]:
    """添加品牌中英文别名的排除列表，保证两边都能匹配。"""
    expanded: set[str] = set(brands)
    for b in brands:
        alias = _BRAND_ALIASES.get(b)
        if alias:
            expanded.add(alias)
    return expand_exclude_brands(list(expanded))


def _scoped_exclude_brands(slots: dict) -> list:
    """Return exclude_brands scoped to the current category, so brand exclusion
    doesn't leak across different categories."""
    category = slots.get("category", "")
    if category:
        by_cat = slots.get("exclude_by_category", {})
        if by_cat and category in by_cat:
            return _expand_brand_aliases(by_cat[category])
    return _expand_brand_aliases(slots.get("exclude_brands") or [])


def _normalize_exclusions(slots: dict) -> None:
    """Move flat exclude_brands into category-scoped exclude_by_category dict."""
    category = slots.get("category", "")
    if not category:
        return  # no category to scope to - keep exclude_brands as-is
    flat = slots.pop("exclude_brands", None)
    if not flat:
        return
    by_cat = dict(slots.get("exclude_by_category") or {})
    existing = set(by_cat.get(category, []))
    existing.update(b for b in flat if b)
    by_cat[category] = list(existing)
    slots["exclude_by_category"] = by_cat


def _build_exclusion_hint(slots: dict) -> str:
    """Build a prompt hint about excluded brands/categories so the LLM can acknowledge them."""
    parts = []
    excluded_brands = _scoped_exclude_brands(slots)
    if excluded_brands:
        parts.append(f"用户已排除品牌：{'、'.join(excluded_brands)}")
    excluded_cats = slots.get("exclude_categories") or []
    if excluded_cats:
        parts.append(f"用户已排除品类：{'、'.join(excluded_cats)}")
    if parts:
        return "用户约束（必须在回复中体现）：" + "；".join(parts) + "\n   -> 不要在「结语」中追问已排除的品牌或品类，如需调整建议提醒用户当前已排除的品牌。\n"
    return ""
