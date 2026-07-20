"""
Scenario shopping - scenario-to-category mapping and category diversification.

Extracted from agent.py.
"""
import logging
import re
from collections import defaultdict

logger = logging.getLogger("agent")


# ── 可用品类列表（启动时从 PostgreSQL / 种子数据加载，场景映射用）──
_AVAILABLE_CATEGORIES: list[str] = []

# ── 场景关键词 -> 品类映射回退表（LLM 失败时使用，确保所有关键词指向已存在品类）──
_SCENARIO_FALLBACK_MAP = {
    "度假": ["防晒", "T恤", "裙装", "跑鞋", "双肩包"],
    "旅行": ["双肩包", "T恤", "跑鞋", "防晒"],
    "三亚": ["防晒", "裙装", "T恤", "跑鞋", "双肩包"],
    "通勤": ["双肩包", "衬衫", "休闲鞋", "外套", "耳机"],
    "露营": ["跑鞋", "外套", "双肩包", "T恤", "手机"],
    "户外": ["外套", "跑鞋", "双肩包", "T恤", "手机"],
    "穿搭": ["T恤", "外套", "裤装", "裙装", "跑鞋"],
    "送礼": ["耳机", "手表", "音箱", "口红", "双肩包"],
    "办公": ["键盘", "办公椅", "双肩包", "平板", "耳机"],
    "健身": ["瑜伽用品", "跑鞋", "T恤", "运动服", "双肩包"],
    "出差": ["双肩包", "衬衫", "外套", "耳机", "平板"],
}


def _get_available_categories() -> list[str]:
    """Return the current available category list, with a lazy-load fallback."""
    if _AVAILABLE_CATEGORIES:
        return _AVAILABLE_CATEGORIES
    # Fallback: return all keys from the fallback map values (deduplicated)
    cats: list[str] = []
    seen: set[str] = set()
    for v in _SCENARIO_FALLBACK_MAP.values():
        for c in v:
            if c not in seen:
                seen.add(c)
                cats.append(c)
    return cats


async def _map_scenario_to_categories(query: str, scenario: str) -> list[str]:
    """将场景化需求映射到商品数据库中 *实际存在* 的品类。

    优先使用 LLM 从可用品类列表中筛选 3-5 个最相关品类；
    LLM 失败时回退到关键词匹配 _SCENARIO_FALLBACK_MAP。
    确保返回的品类名都是实际可检索的品类。
    """
    categories = _AVAILABLE_CATEGORIES or _get_available_categories()

    prompt = f"""用户描述了一个购物场景：「{query}」。
请从以下可用品类列表中选择 3-5 个与该场景最相关的品类，用于商品检索。

可用品类（{len(categories)}个）：{', '.join(sorted(categories))}

规则：
1. 只输出上面列表中的品类名，严禁编造不存在的品类
2. 优先选择与场景直接相关的品类
3. 如果没有完美匹配的，选择语义/功能最接近的品类（如没有"沙滩鞋"则选"跑鞋"或"凉鞋"）
4. 每行一个品类名，最多 5 行，不要编号和额外文字"""

    try:
        from app.services.llm_client import fast_chat_completion
        raw = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=100,
        )
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
        # Filter out numbered/bullet prefixes
        lines = [re.sub(r'^[\d]+[\.\)、\s]+', '', l).strip() for l in lines]
        lines = [re.sub(r'^[-•\*●]\s*', '', l).strip() for l in lines]
        lines = [l for l in lines if 1 <= len(l) <= 80]
        # Only keep lines that match an available category
        cat_set = set(categories)
        valid = [l for l in lines if l in cat_set]
        if valid:
            logger.info("Scenario->Category mapped: %s -> %s", scenario, valid[:5])
            return valid[:5]
        # LLM returned non-matching: try fuzzy match
        if lines:
            fuzzy = _fuzzy_match_categories(lines, categories)
            if fuzzy:
                return fuzzy[:5]
    except Exception as e:
        logger.warning("Scenario->Category LLM mapping failed: %s", e)

    # Keyword fallback: scan query for scenario keywords -> map to available categories
    q_lower = query.lower()
    matched_cats: list[str] = []
    seen: set[str] = set()
    # Longest keyword first for most specific match
    for keyword in sorted(_SCENARIO_FALLBACK_MAP.keys(), key=len, reverse=True):
        if keyword in q_lower:
            for c in _SCENARIO_FALLBACK_MAP[keyword]:
                if c not in seen:
                    seen.add(c)
                    matched_cats.append(c)

    if matched_cats:
        logger.info("Scenario->Category fallback (keyword): %s -> %s", scenario, matched_cats[:5])
        return matched_cats[:5]

    # Ultimate fallback: return the query itself for semantic search
    logger.info("Scenario->Category: no mapping found, using raw query")
    return [query]


def _fuzzy_match_categories(candidate_names: list[str], valid_categories: list[str]) -> list[str]:
    """Fuzzy-match LLM-output category names against the valid category list."""
    result: list[str] = []
    seen: set[str] = set()
    for name in candidate_names:
        if name in seen:
            continue
        # Exact match first
        if name in valid_categories:
            result.append(name)
            seen.add(name)
            continue
        # Substring match: if candidate contains a valid category or vice versa
        for cat in valid_categories:
            if cat in name or name in cat:
                if cat not in seen:
                    result.append(cat)
                    seen.add(cat)
                break
    return result


def _pre_diversify_by_category(chunks: list, max_per_category: int = 3) -> list:
    """按品类分组，每组取 top-N（按 semantic score），交替采样合并。

    用于场景化购物在 reranker 全局排序之前保持品类多样性。
    每个品类保留 max_per_category 个最优候选，然后跨品类交替拼接。
    """
    if not chunks:
        return []
    groups: dict[str, list] = defaultdict(list)
    for c in chunks:
        cat = (c.get("payload", {}) or {}).get("category", "") or "其他"
        groups[cat].append(c)

    # 每组按 score 降序，取前 max_per_category
    for cat in groups:
        groups[cat] = sorted(groups[cat],
                            key=lambda x: x.get("score", 0), reverse=True)[:max_per_category]

    # 交替采样：轮询各品类取第1个，再取第2个...
    result: list = []
    max_rounds = max(len(v) for v in groups.values())
    for rnd in range(max_rounds):
        for cat in sorted(groups.keys()):
            if rnd < len(groups[cat]):
                result.append(groups[cat][rnd])

    logger.info("Pre-diversify: %d chunks -> %d (across %d categories)",
                len(chunks), len(result), len(groups))
    return result
