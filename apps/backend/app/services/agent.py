"""
Agent 编排 — LangGraph StateGraph 工作流
流程: classify_intent → (missing_slots? → clarify → generate | retrieve → generate) → SSE stream
"""
import hashlib
import json
import logging
import time
from typing import TypedDict, AsyncGenerator
from langgraph.graph import StateGraph, END
from app.services.intent import classify_intent, extract_slots, rewrite_query, extract_negation_slots
from app.services.rag import retrieve as rag_retrieve
from app.services.reranker import rerank_async
from app.services.llm_client import chat_completion
from app.schemas.sse_events import TextDeltaEvent, ProductCardEvent, DoneEvent, ErrorEvent, ProgressEvent, WebSearchResultEvent
from app.core.config import settings
from app.services.web_search import search_web, format_search_results, WEB_SEARCH_PROMPT, WEB_SEARCH_FALLBACK_PROMPT
from app.services import cache
from app.services import state_manager as sm
from app.services import cart_service
from app.services.exclusion_rules import (
    expand_exclude_brands,
    normalize_exclusion_slots,
    product_violates_exclusions,
)
import re

logger = logging.getLogger("agent")


# ── State ──

class AgentState(TypedDict, total=False):
    query: str
    session_id: str
    cart_session_id: str
    user_id: str
    intent: str
    confidence: float
    slots: dict
    category_context: dict
    negation_slots: dict  # 否定条件：exclude_brands, exclude_categories, exclude_attributes
    rewritten_query: str
    retrieved_chunks: list
    latency_ms: float
    response: str
    product_cards: list
    cart_action: str  # cart operation: add/remove/view/clear/checkout
    cart_product_id: str
    cart_quantity: int
    error: str
    history: list  # 多轮对话历史 [{role, content}, ...]


# ── Nodes ──

async def node_classify_intent(state: AgentState) -> AgentState:
    """意图分类 + 槽位填充 + 短词扩展"""
    query = state["query"]

    if not query or not query.strip():
        state["intent"] = "chitchat"
        state["confidence"] = 1.0
        state["slots"] = {}
        return state

    # 查询扩展：短查询(≤6字)或明显查询类意图时展开关键词提升检索召回
    expanded = query
    if len(query.strip()) <= 6:
        expanded = await _expand_short_query(query)
        logger.info("Short query expanded: '%s' → '%s'", query, expanded)

    # 标记是否已扩展，供下游 clarify 判断跳过追问
    state["_query_was_expanded"] = (expanded != query)

    history = state.get("history", []) or []
    ctx = ""
    if history:
        recent = history[-4:]  # 最近4条
        lines = [f"{'用户' if m.get('role')=='user' else '助手'}：{(m.get('content') or '')[:120]}" for m in recent]
        ctx = "\n对话上文：\n" + "\n".join(lines)
    intent_result = await classify_intent(expanded if expanded != query else query, context=ctx)
    state["intent"] = intent_result["intent"]
    state["confidence"] = intent_result["confidence"]

    # 非闲聊意图才提取槽位（用原始查询，关键词堆会污染 LLM 槽位提取）
    if state["intent"] != "chitchat":
        slots = await extract_slots(query, state["intent"])
        _apply_query_category_hint(slots, query)
        _apply_history_category_hint(slots, state.get("history", []))

        # 合并历史上下文：保留上一轮的排除条件，本轮的偏好覆盖历史
        prev_slots = _previous_slots_from_state(state)
        category_changed = _has_category_change(prev_slots, slots)
        prev_slots = _prune_previous_slots_for_category_change(prev_slots, slots)
        merged = {}
        # 排除类字段：累积（不丢失上一轮的排除条件）
        for key in ("exclude_brands", "exclude_categories", "exclude_attributes"):
            prev_val = prev_slots.get(key)
            new_val = slots.get(key)
            if isinstance(prev_val, list) and isinstance(new_val, list):
                merged[key] = list(set(prev_val + new_val))
            elif isinstance(prev_val, dict) and isinstance(new_val, dict):
                merged[key] = {**prev_val, **new_val}
            else:
                merged[key] = new_val or prev_val
        # 偏好类字段：本轮覆盖历史（跳过 None，不覆盖历史有效值）
        for key in slots:
            if key not in merged and slots[key] is not None:
                merged[key] = slots[key]
        # 保留本轮未涉及的历史偏好（跳过 None）
        for key in prev_slots:
            if key not in merged and prev_slots[key] is not None:
                merged[key] = prev_slots[key]

        state["slots"] = merged
        state["_category_changed"] = category_changed
        state["category_context"] = _update_category_context(state.get("category_context", {}), merged)

        # 否定语义：任何含否定关键词的查询都提取排除条件（不只 anti_selection）
        neg_keywords = ["不要", "除了", "非", "不含", "排除", "拒绝", "去掉", "避开", "别", "讨厌", "不喜欢", "反感"]
        has_negation = any(kw in query for kw in neg_keywords)
        if state["intent"] == "anti_selection" or has_negation:
            negation = await extract_negation_slots(query)
            # 合并而非覆盖 — 保留 merge loop 已累积的历史排除条件
            neg_brands = negation.get("exclude_brands") or []
            existing_brands = state["slots"].get("exclude_brands") or []
            state["slots"]["exclude_brands"] = list(set(existing_brands + neg_brands))

            neg_cats = negation.get("exclude_categories") or []
            existing_cats = state["slots"].get("exclude_categories") or []
            state["slots"]["exclude_categories"] = list(set(existing_cats + neg_cats))

            neg_attrs = negation.get("exclude_attributes") or {}
            existing_attrs = state["slots"].get("exclude_attributes") or {}
            state["slots"]["exclude_attributes"] = {**existing_attrs, **neg_attrs}

            # 补充关键词提取的文本级排除词（LLM 可能不返回此字段）
            from app.services.intent import _keyword_extract_negation
            kw_neg = _keyword_extract_negation(query)
            state["slots"]["exclude_text_terms"] = kw_neg.get("exclude_text_terms", [])
            # LLM 未覆盖的排除项，用关键词结果补充
            if not state["slots"]["exclude_brands"] and kw_neg.get("exclude_brands"):
                state["slots"]["exclude_brands"] = list(set(state["slots"]["exclude_brands"] + kw_neg["exclude_brands"]))
            if not state["slots"]["exclude_attributes"] and kw_neg.get("exclude_attributes"):
                state["slots"]["exclude_attributes"] = {**state["slots"]["exclude_attributes"], **kw_neg["exclude_attributes"]}

            logger.info("Negation extracted: brands=%s, attrs=%s, text_terms=%s",
                        state["slots"]["exclude_brands"],
                        state["slots"]["exclude_attributes"],
                        state["slots"].get("exclude_text_terms"))

        # 品类隔离：排除品牌只影响当前品类，不越界到其他品类
        _normalize_exclusions(state["slots"])
        _sanitize_slots_for_category(state["slots"])

        # 改写查询：排除类多轮请求使用继承后的品类召回，避免被排除品牌词牵引向量检索。
        base = _build_rewrite_base(query, expanded, state["slots"], has_negation, negation if has_negation else {})
        rewritten = await rewrite_query(base, state["slots"])
        state["rewritten_query"] = rewritten
    else:
        state["slots"] = {}

    return state


async def _expand_short_query(query: str) -> str:
    """将短关键词扩展为包含主要子品类的检索查询，提升向量召回率。

    "鞋" → "运动鞋 休闲鞋 皮鞋 跑步鞋 鞋类推荐"
    "平板" → "平板电脑 iPad 安卓平板 华为平板 推荐"
    """
    prompt = f"""用户输入了一个非常短的商品搜索词：「{query}」

这个搜索词太短，缺乏语义上下文，会导致商品检索效果很差。请你分析这个词可能指代的商品品类，列出该品类下最常见的 5-8 个子品类或相关热门搜索词，用空格分隔。

例如：
- "鞋" → "运动鞋 休闲鞋 皮鞋 跑步鞋 篮球鞋 帆布鞋 鞋类推荐"
- "平板" → "平板电脑 iPad 安卓平板 华为平板 小米平板 学习平板"
- "耳机" → "蓝牙耳机 降噪耳机 无线耳机 头戴式耳机 入耳式耳机 运动耳机"

只输出扩展后的搜索词（一行纯文本），不要输出其他内容。"""

    try:
        from app.services.llm_client import fast_chat_completion
        result = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=80,
        )
        expanded = result.strip().strip('"').strip("'")
        if expanded and len(expanded) > len(query) + 2:
            logger.info("Short query expanded: '%s' → '%s'", query, expanded)
            return expanded
    except Exception as e:
        logger.warning("Short query expansion failed for '%s': %s", query, e)

    return query


async def node_clarify(state: AgentState) -> AgentState:
    """反问节点：缺失关键信息时，生成追问问题"""
    slots = state.get("slots", {})
    missing = slots.get("missing_slots", [])
    category = slots.get("category", "")

    if not missing and not category:
        # 极短模糊词：无品类无缺失槽位，生成通用追问
        query = state.get("query", "")
        prompt = f"""你是一个电商导购助手。用户说：「{query}」，没有指定具体想买什么。

请生成一个简短、友好的追问问题（1-2句话，不超过60字），引导用户说出想购买的商品品类或需求。
只输出问题本身，不要加任何解释、不要打招呼。"""
        try:
            from app.services.llm_client import fast_chat_completion
            raw = await fast_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=100,
            )
            state["response"] = raw.strip()
            if state["response"]:
                return state
        except Exception as e:
            logger.warning("Clarify LLM failed for ultra-vague: %s", e)
        state["response"] = "能再具体说说您的需求吗？比如想买什么品类、预算多少呢？"
        return state

    query = state["query"]
    intent = state.get("intent", "commodity_recommend")

    if missing:
        missing_str = "、".join(missing)
        prompt = f"""你是一个电商导购助手。用户刚才说：「{query}」，但缺少以下关键信息：{missing_str}。

请生成一个简短、友好的追问问题（1-2句话，不超过60字），引导用户补充缺失的信息。
只输出问题本身，不要加任何解释、不要打招呼，不要使用"当然可以""好的"等开头。"""
    else:
        # missing 为空但有 category：仅含品类短词，追问细化需求
        prompt = f"""你是一个电商导购助手。用户想买{category}类商品，但没说具体需求。

请生成一个简短、友好的追问问题（1-2句话，不超过60字），引导用户细化需求（如预算、用途、偏好等）。
只输出问题本身，不要加任何解释、不要打招呼，不要使用"当然可以""好的"等开头。"""

    try:
        from app.services.llm_client import fast_chat_completion
        raw = await fast_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100,
        )
        state["response"] = raw.strip()
    except Exception as e:
        logger.warning("Clarify LLM failed, using template: %s", e)
        if missing:
            clarify_map = {
                "品类": "请问您想购买什么品类的商品呢？",
                "价格": "请问您的预算大概是多少呢？",
                "品牌": "请问您有偏好的品牌吗？",
                "场景": "请问是买来做什么用的呢？",
                "用途": "请问您主要用来做什么呢？",
                "规格": "请问您对规格有什么要求吗？",
                "风格": "请问您偏好什么风格呢？",
                "材质": "请问对材质有特别要求吗？",
                "功能": "请问您最看重哪些功能呢？",
                "颜色": "请问您偏好什么颜色呢？",
            }
            question = None
            for key, tmpl in clarify_map.items():
                if any(key in m for m in missing):
                    question = tmpl
                    break
            state["response"] = question or f"能再具体说说您的需求吗？比如{'、'.join(missing)}。"
        else:
            state["response"] = f"您想要什么类型的{category}呢？比如预算、用途方面有什么偏好吗？"

    state["_clarify_done"] = True
    logger.info("Clarify: missing=%s category=%s → response=%s", missing, category, state["response"])
    return state


# ── 可用品类列表（启动时从 Qdrant / 种子数据加载，场景映射用）──
_AVAILABLE_CATEGORIES: list[str] = []

# ── 场景关键词 → 品类映射回退表（LLM 失败时使用，确保所有关键词指向已存在品类）──
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
        import re
        lines = [re.sub(r'^[\d]+[\.\)、\s]+', '', l).strip() for l in lines]
        lines = [re.sub(r'^[-•\*●]\s*', '', l).strip() for l in lines]
        lines = [l for l in lines if 1 <= len(l) <= 80]
        # Only keep lines that match an available category
        cat_set = set(categories)
        valid = [l for l in lines if l in cat_set]
        if valid:
            logger.info("Scenario→Category mapped: %s → %s", scenario, valid[:5])
            return valid[:5]
        # LLM returned non-matching: try fuzzy match
        if lines:
            fuzzy = _fuzzy_match_categories(lines, categories)
            if fuzzy:
                return fuzzy[:5]
    except Exception as e:
        logger.warning("Scenario→Category LLM mapping failed: %s", e)

    # Keyword fallback: scan query for scenario keywords → map to available categories
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
        logger.info("Scenario→Category fallback (keyword): %s → %s", scenario, matched_cats[:5])
        return matched_cats[:5]

    # Ultimate fallback: return the query itself for semantic search
    logger.info("Scenario→Category: no mapping found, using raw query")
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
    from collections import defaultdict
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

    logger.info("Pre-diversify: %d chunks → %d (across %d categories)",
                len(chunks), len(result), len(groups))
    return result


async def node_retrieve(state: AgentState) -> AgentState:
    """RAG 检索"""
    if state["intent"] == "chitchat":
        state["retrieved_chunks"] = []
        return state

    query = state.get("rewritten_query") or state["query"]
    slots = state.get("slots", {})

    # 场景化购物：映射为已存在品类 → 分别检索 → 品类感知预采样 → 合并
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
            logger.info("Reranker applied: %d → %d chunks re-ranked", n_before, len(state["retrieved_chunks"]))
        except Exception as e:
            logger.warning("Reranker unavailable, using raw retrieval: %s", e)

    logger.info("Agent retrieved %d chunks in %.0fms", len(state["retrieved_chunks"]), state["latency_ms"])
    return state


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
# 共享辅助函数 — 消除 node_generate / generate_response 重复
# ═══════════════════════════════════════════════════════

def _extract_raw_products(chunks: list, limit: int = 10) -> list[dict]:
    """从 Qdrant chunks 提取原始商品属性列表"""
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


_SLOT_KEYS = {
    "category", "price_min", "price_max", "brand_preference", "attributes",
    "scenario", "exclude_brands", "exclude_categories", "exclude_attributes",
    "exclude_text_terms", "exclude_by_category", "missing_slots",
}


def _build_rewrite_base(query: str, expanded: str, slots: dict, has_negation: bool, negation: dict) -> str:
    if has_negation and slots.get("category"):
        return f"{slots['category']} 热门推荐 同类商品"
    positive_q = (negation or {}).get("positive_query", "") if has_negation else ""
    return _strip_cross_category_noise(positive_q or expanded or query, slots)


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
    logger.info("Category changed %s → %s, pruned category-scoped preferences", prev_category, new_category)
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


def _previous_slots_from_state(state: dict) -> dict:
    """Read slots from current nested state and legacy top-level session fields.

    Defensively strips keys that leaked from old session state nesting contamination
    (intent, product_cards, nested slots dict, etc.) so they don't pollute the new
    merged slots and cause cross-category exclusion leakage.
    """
    nested = state.get("slots")
    if isinstance(nested, dict):
        prev = dict(nested)
        # 清除因旧版 state→slots 嵌套导致的脏数据泄露
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


# 品牌中英文别名映射 — 解决 Qdrant 中同一品牌中英文名不一致导致排除失效的问题
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
        return  # no category to scope to — keep exclude_brands as-is
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
        return "用户约束（必须在回复中体现）：" + "；".join(parts) + "\n   → 不要在「结语」中追问已排除的品牌或品类，如需调整建议提醒用户当前已排除的品牌。\n"
    return ""


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


def _build_generation_prompt(message: str, slots: dict, valid_ranked: list, is_reliable: bool, intent: str, history: list[dict] | None = None) -> str:
    """构建 LLM 生成推荐回复的 prompt（统一版本，支持多轮上下文）"""
    reliability_hint = ""
    if not is_reliable:
        reliability_hint = "\n⚠️ 注意：以下商品与用户需求的匹配度较低，请在回复中诚实告知用户，建议其调整搜索条件。\n"

    scenario_hint = ""
    if intent == "scenario_shopping":
        scene = slots.get("scenario", "") or "购物场景"
        # 从排序结果中提取实际品类名用于动态示例
        scene_categories = list(dict.fromkeys(
            r.get("category", "") for r in valid_ranked if r.get("category")
        ))
        cat_example = "+".join(scene_categories[:4]) if len(scene_categories) >= 2 else "品类1+品类2"
        scenario_hint = (
            f"场景化推荐模式：用户场景为「{scene}」，商品已按品类多样化筛选。\n"
            "请按品类分组推荐（每个品类介绍 1 款最优商品），说明每件商品在该场景中的角色与搭配逻辑。\n"
            f"开头用一句话概述搭配方案（如'为您搭配{scene}方案：{cat_example}'），再逐品展开。\n"
            "严禁编造不存在的品类组合 — 只能基于下方检索到的实际商品及其品类。\n"
        )

    # 多轮对话历史
    history_text = ""
    if history:
        history_lines = []
        for h in history:
            role_label = "用户" if h["role"] == "user" else "助手"
            history_lines.append(f"{role_label}：{h['content']}")
        history_text = "\n对话历史：\n" + "\n".join(history_lines) + "\n\n请结合以上对话历史理解当前用户需求。比如用户说「便宜一点的」是在前面推荐的基础上筛选，用户说「要红色的」是在补充颜色偏好。如果当前问题含义模糊，根据历史推断具体意图。\n"

    context_parts = []
    for i, r in enumerate(valid_ranked):
        match_pct = round(r.get("match_score", 0) * 100)
        context_parts.append(
            f"[{i+1}] {r.get('title')} | ¥{r.get('price')} | ★{r.get('rating')} | "
            f"品类:{r.get('category','?')} | 匹配度{match_pct}% | {' '.join(r.get('highlights', [])[:2])} | {r.get('rank_reason', '')}"
        )
    context = "\n".join(context_parts)
    n = len(valid_ranked)

    # 场景模式使用独立的输出格式指令
    if intent == "scenario_shopping":
        format_section = f"""输出格式要求（场景推荐专用，严格遵守）：

第一步：开头用一句话概述搭配方案（用检索到的品类名替换），以句号结尾。
第二步：按品类分组推荐，每组用「品类名·商品N」独占一行作为标题。
第三步：以「结语」收尾，简短追问用户偏好（1句话，不超过20字）。

每款商品的展开格式：
「品类名·商品N」
商品全名 | 综合匹配度 XX%（使用检索数据中的匹配度数值，如实输出）
① 搭配角色：该商品在场景中的作用与价值
② 品质亮点：核心卖点与关键参数
③ 适用场景：在场景中的具体使用时机

要求：
- 必须逐一推荐以上全部 {n} 款商品，不可跳过任何一款
- 每款商品必须独占一行使用「品类名·商品N」标记
- 品类名从检索数据中提取，不得编造
- 总字数控制在400字以内
- 禁止使用"非常好""很不错"等模糊词，必须引用具体数字"""
    else:
        format_section = f"""输出格式要求（严格遵守，违反将导致推荐无效）：

第一步：开头用一句话总结，列出全部商品名称（用顿号分隔），以句号结尾。
第二步：紧接着依次用「商品1」「商品2」「商品3」分别展开每款商品，每款商品用「商品N」独占一行作为标题。
第三步：以「结语」收尾，简短追问用户偏好（1句话，不超过20字）。

每款商品的展开格式：
「商品N」
商品全名 | 综合匹配度 XX%（使用上方检索数据中的匹配度数值，如实输出，不得编造）
① 匹配依据：...
② 品质亮点：...
③ 适用场景：...

格式示例：
为您找到3款降噪耳机：索尼WH-1000XM5、Bose QC45、AirPods Pro，分别适合不同场景。

「商品1」
索尼 WH-1000XM5 | 综合匹配度 92%
① 匹配依据：顶级降噪，适合通勤与办公
② 品质亮点：30小时续航、LDAC高清音频、多点连接
③ 适用场景：地铁通勤、办公室专注工作

「商品2」
Bose QC45 | 综合匹配度 88%
① 匹配依据：性价比突出的降噪标杆，通勤续航双优
② 品质亮点：24小时续航、TriPort声学结构、蓝牙5.1
③ 适用场景：日常通勤与长时间佩戴

「商品3」
AirPods Pro | 综合匹配度 85%
① 匹配依据：苹果生态无缝切换，自适应降噪
② 品质亮点：H2芯片、个性化空间音频、IPX4防水
③ 适用场景：苹果用户日常全场景使用

「结语」需要进一步筛选品牌或预算吗？

要求：
- 必须逐一推荐以上全部 {n} 款商品，不可跳过任何一款
- 每款商品必须独占一行使用「商品N」标记
- 总字数控制在300字以内
- 禁止使用"非常好""很不错"等模糊词，必须引用具体数字"""

    return f"""你是一个电商导购助手。基于检索到的商品信息，为用户生成推荐回答。
{reliability_hint}
{scenario_hint}{history_text}⚠️ 严禁事项（违反将导致推荐无效）:
1. 不得编造任何商品名称、型号、价格 — 只能引用上方[1][2]...标记的商品
2. 不得编造优惠券、满减、折扣、赠品、限时活动
3. 不得编造不存在的功能参数、认证标识
4. 不得编造用户评价、销量排名、市场占有率、对比结论

校验规则:
- 你提到的每个价格数字，必须在检索数据中出现过
- 你提到的每个品牌名、产品名，必须在检索数据中出现过
- 如果所有商品与用户需求的匹配度均低于60%，应诚实告知"当前没有很匹配的商品，建议调整条件"
- 违反以上任一条，不要输出该推荐

用户需求：{message}
用户预算：{slots.get('price_min', '不限')}-{slots.get('price_max', '不限')}
用户品类偏好：{slots.get('category', '未指定')}
{_build_exclusion_hint(slots)}
检索到的商品（共{n}款，必须全部推荐，不可遗漏）：
{context}

{format_section}"""


async def node_generate(state: AgentState) -> AgentState:
    """生成回答 + 商品卡片"""
    if state.get("_clarify_done"):
        state["product_cards"] = []
        return state

    if state.get("intent") == "cart_operation" and state.get("response"):
        state["product_cards"] = state.get("product_cards", [])
        return state

    if state["intent"] == "chitchat":
        state["response"] = "你可以告诉我具体的需求，比如「推荐一款降噪耳机」「300元以内的运动鞋」「送女朋友的生日礼物」，我会帮你找到合适的商品～"
        state["product_cards"] = []
        return state

    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        state["response"] = "抱歉，暂时没有找到符合您要求的商品。可以试试调整条件重新搜索吗？"
        state["product_cards"] = []
        return state

    from app.services.product_ranker import rank_products

    raw_products = _extract_raw_products(chunks)
    raw_products = _filter_products_by_requested_category(raw_products, state.get("slots", {}).get("category", ""))
    raw_products = _filter_products_by_exclusions(raw_products, state.get("slots", {}))
    user_prefs = _build_user_prefs(state.get("slots", {}))
    ranked = rank_products(raw_products, user_prefs, state["intent"], top_k=3)
    valid_ranked, is_reliable = _validate_ranked_products(ranked)

    if not valid_ranked:
        state["response"] = "抱歉，暂时没有找到符合您要求的商品。可以试试调整条件重新搜索吗？"
        state["product_cards"] = []
        return state

    cards = _assemble_cards(valid_ranked)
    state["product_cards"] = cards
    state["_is_reliable"] = is_reliable

    prompt = _build_generation_prompt(state["query"], state.get("slots", {}), valid_ranked, is_reliable, state["intent"], history=state.get("history", []))

    try:
        stream = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
            stream=True,
        )
        response_text = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content
        state["response"] = response_text
    except Exception as e:
        logger.error("LLM generate failed: %s", e)
        state["response"] = f"为您找到 {len(cards)} 款相关商品。如需进一步筛选，请告诉我您的偏好。"
    return state


# ── Cart Helpers ──

def _extract_cart_action(query: str) -> str:
    """从用户查询中提取购物车操作类型"""
    q = query.lower()
    if any(kw in q for kw in ["加入购物车", "加到购物车", "加购", "放入购物车", "拍下"]):
        return "add"
    if any(kw in q for kw in ["剩下", "其余", "余下", "剩余"]) and any(kw in q for kw in ["买", "购买", "加入"]):
        return "add"
    quantity_patterns = [
        r"(?:数量|数目|件数|个数)",
        r"(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成)\s*[0-9一二两三四五六七八九十]",
        r"(?:买|要|来)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
        r"(?:加|增加|再加|多买|减|减少|少买|去掉)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
        r"(?:加|增加|再加|多买|减|减少|少买|去掉).{0,6}?(?:到|为|成)\s*[0-9一二两三四五六七八九十]+\s*(?:件|个|台|本|双|套|份)",
    ]
    if any(re.search(pattern, q) for pattern in quantity_patterns):
        return "quantity"
    if any(kw in q for kw in ["清空", "全部删除", "全部移除"]):
        return "clear"
    if any(kw in q for kw in ["下单", "结算", "结账", "支付", "买单", "确认下单"]):
        return "checkout"
    if any(kw in q for kw in ["删除", "移除", "去掉", "不要第"]):
        return "remove"
    if any(kw in q for kw in ["查看", "看看", "显示", "我的购物车", "购物车里有"]):
        return "view"
    if any(kw in q for kw in ["加入", "加购", "加到", "添加", "放入", "加一个", "加第"]):
        return "add"
    return "view"  # 默认查看


def _parse_quantity(query: str) -> int | None:
    """解析“设置为 N 件”类绝对数量。"""
    clear_match = re.search(
        r"(?:买|要|来|加购|加入|放入|加到|拍)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|只|双|套|份)",
        query,
        re.I,
    )
    if clear_match:
        return _quantity_token_to_int(clear_match.group(1))

    patterns = [
        r"(?:数量|数目|件数|个数).{0,8}?(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成|到|为)?\s*([0-9]+|[一二两三四五六七八九十]+)",
        r"(?:改成|改为|设为|设置为|调整为|调为|调到|改到|变成)\s*([0-9]+|[一二两三四五六七八九十]+)",
        r"(?:减|减少|少买|加|增加|多买).{0,6}?(?:到|为|成)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        r"(?:买|要|来)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.I)
        if match:
            return _quantity_token_to_int(match.group(1))

    for match in re.finditer(r"([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)", query, re.I):
        if match.start() > 0 and query[match.start() - 1] == "第":
            continue
        return _quantity_token_to_int(match.group(1))

    return None


def _parse_quantity_delta(query: str) -> int | None:
    """解析“加一件/减两件”类相对数量。"""
    match = re.search(
        r"(?:加|增加|再加|多买)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        query,
        re.I,
    )
    if match:
        return _quantity_token_to_int(match.group(1))

    match = re.search(
        r"(?:减|减少|少买|去掉)\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:件|个|台|本|双|套|份)",
        query,
        re.I,
    )
    if match:
        value = _quantity_token_to_int(match.group(1))
        return -value if value is not None else None

    return None


def _quantity_token_to_int(raw: str) -> int | None:
    clear_cn_nums = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if raw in clear_cn_nums:
        return clear_cn_nums[raw]
    if raw == "十":
        return 10
    if raw.startswith("十") and len(raw) == 2:
        return 10 + clear_cn_nums.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return clear_cn_nums.get(raw[0], 0) * 10
    if "十" in raw and len(raw) == 3:
        return clear_cn_nums.get(raw[0], 0) * 10 + clear_cn_nums.get(raw[2], 0)
    if raw.isdigit():
        return max(0, int(raw))
    cn_nums = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if raw == "十":
        return 10
    if raw.startswith("十") and len(raw) == 2:
        return 10 + cn_nums.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return cn_nums.get(raw[0], 0) * 10
    if "十" in raw and len(raw) == 3:
        return cn_nums.get(raw[0], 0) * 10 + cn_nums.get(raw[2], 0)
    return cn_nums.get(raw)


def _resolve_remaining_product_card(query: str, product_cards: list[dict]) -> dict | None:
    """Resolve fuzzy references like "排除前两个，剩下的那个加购"."""
    if not product_cards:
        return None
    remaining_markers = ("剩下", "其余", "余下", "剩余", "留下")
    exclude_markers = ("排除", "不要", "去掉", "剔除", "除了", "删掉")
    if not any(marker in query for marker in remaining_markers):
        return None
    if not any(marker in query for marker in exclude_markers):
        return product_cards[0] if len(product_cards) == 1 else None

    excluded: set[int] = set()
    if re.search(r"(前|头)\s*(?:2|二|两)\s*(?:个|件|款|项)?", query):
        excluded.update([0, 1])
    elif re.search(r"(前|头)\s*(?:3|三)\s*(?:个|件|款|项)?", query):
        excluded.update([0, 1, 2])
    elif re.search(r"(前|头)\s*(?:1|一)\s*(?:个|件|款|项)?", query):
        excluded.add(0)

    ordinal_map = {"一": 0, "1": 0, "二": 1, "两": 1, "2": 1, "三": 2, "3": 2, "四": 3, "4": 3, "五": 4, "5": 4}
    for token, idx in ordinal_map.items():
        if re.search(rf"(?:第\s*{re.escape(token)}|{re.escape(token)}\s*号)", query):
            excluded.add(idx)

    remaining = [card for idx, card in enumerate(product_cards) if idx not in excluded]
    return remaining[0] if len(remaining) == 1 else None


def _product_from_card(card: dict) -> dict:
    return {
        "id": str(card.get("product_id") or card.get("id", "")).strip(),
        "title": card.get("title", ""),
        "price": card.get("price", 0),
    }


def _get_cart_backref_cards(state: "AgentState") -> list[dict]:
    product_cards = state.get("product_cards", []) or []
    slots = state.get("slots", {}) or {}
    prev_cards = slots.get("product_cards", []) or []
    return product_cards or prev_cards or []


def _find_products_for_multi_cart(query: str, state: "AgentState") -> list[dict]:
    """Resolve multi-item cart commands such as "这两款都加入购物车" from current cards."""
    product_cards = _get_cart_backref_cards(state)
    if not product_cards:
        return []

    normalized = re.sub(r"\s+", "", query)
    indices, _indices_error = _extract_cart_item_indices(query, len(product_cards))
    if len(indices) >= 2:
        selected: list[dict] = []
        seen: set[str] = set()
        for idx in indices:
            card = product_cards[idx]
            product = _product_from_card(card)
            if product["id"] and product["id"] not in seen:
                seen.add(product["id"])
                selected.append(product)
        return selected

    multi_markers = ("都", "全部", "全都", "一起", "这两款", "这两个", "两款", "两个", "前两", "前三")
    if not any(marker in normalized for marker in multi_markers):
        return []

    limit = len(product_cards)
    if any(marker in normalized for marker in ("这两款", "这两个", "两款", "两个", "前两")):
        limit = min(2, len(product_cards))
    elif "前三" in normalized:
        limit = min(3, len(product_cards))

    selected: list[dict] = []
    seen: set[str] = set()
    for card in product_cards[:limit]:
        product = _product_from_card(card)
        if product["id"] and product["id"] not in seen:
            seen.add(product["id"])
            selected.append(product)
    return selected


def _cart_item_matches_query(item, query: str) -> bool:
    normalized_query = re.sub(r"\s+", "", query.lower())
    normalized_title = re.sub(r"\s+", "", (item.title or "").lower())
    brand = re.sub(r"\s+", "", (getattr(item, "brand", None) or "").lower())
    category = re.sub(r"\s+", "", (getattr(item, "category", None) or "").lower())

    if normalized_title and normalized_title[:4] in normalized_query:
        return True
    if brand and brand in normalized_query:
        return True
    if category and category in normalized_query:
        return True

    ignored = {
        "购物车", "里面", "里的", "商品", "数量", "改成", "改为", "设为", "设置为",
        "调整为", "调到", "改到", "变成", "买", "要", "来", "加", "减", "件", "个",
        "第一", "第二", "第三", "第四", "第五",
    }
    candidates = set()
    for part in re.findall(r"[\u4e00-\u9fff]{2,}", normalized_query):
        for length in range(min(6, len(part)), 1, -1):
            for start in range(0, len(part) - length + 1):
                token = part[start:start + length]
                if token not in ignored and not any(stop in token for stop in ignored):
                    candidates.add(token)
    candidates.update(re.findall(r"[a-z0-9]{2,}", normalized_query))

    return any(token in normalized_title for token in candidates)


def _extract_cart_item_index(query: str, item_count: int) -> tuple[int | None, str | None]:
    ordinal_map = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    match = re.search(r"第\s*([一二两三四五12345])\s*(?:个|件|项|款|样|种)?", query)
    if not match:
        match = re.search(r"([一二两三四五12345])\s*号", query)
    if not match:
        return None, None

    idx = ordinal_map.get(match.group(1))
    if idx is None:
        return None, None
    if idx > item_count:
        return None, f"购物车只有 {item_count} 件商品，没有第 {idx} 个。"
    return idx - 1, None


def _extract_cart_item_indices(query: str, item_count: int) -> tuple[list[int], str | None]:
    normalized = re.sub(r"\s+", "", query)
    if any(marker in normalized for marker in ("全部", "所有", "全都", "整车")):
        return list(range(item_count)), None

    if re.search(r"(?:前|头)(?:2|二|两)(?:个|件|款|项)?", normalized):
        if item_count < 2:
            return [], f"购物车只有 {item_count} 件商品，没有前 2 个。"
        return list(range(2)), None
    if re.search(r"(?:前|头)(?:3|三)(?:个|件|款|项)?", normalized):
        if item_count < 3:
            return [], f"购物车只有 {item_count} 件商品，没有前 3 个。"
        return list(range(3)), None

    ordinal_map = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    found: list[int] = []
    for token, number in ordinal_map.items():
        patterns = (
            rf"第{re.escape(token)}(?:个|件|项|款|样|种)?",
            rf"{re.escape(token)}号",
        )
        if any(re.search(pattern, normalized) for pattern in patterns):
            if number > item_count:
                return [], f"购物车只有 {item_count} 件商品，没有第 {number} 个。"
            found.append(number - 1)

    compact_ordinals = re.findall(r"第([一二两三四五12345]{2,})(?:个|件|项|款|样|种)?", normalized)
    for group in compact_ordinals:
        for char in group:
            number = ordinal_map.get(char)
            if number is None:
                continue
            if number > item_count:
                return [], f"购物车只有 {item_count} 件商品，没有第 {number} 个。"
            found.append(number - 1)

    deduped = sorted(set(found))
    return deduped, None


async def _find_product_for_cart(query: str, state: "AgentState") -> dict | None:
    """从查询中识别用户要加购的商品。
    优先级：1. 序号匹配 product_cards  2. 商品名匹配 product_cards  3. Qdrant 搜索
    """
    product_cards = _get_cart_backref_cards(state)

    remaining_card = _resolve_remaining_product_card(query, product_cards)
    if remaining_card:
        return _product_from_card(remaining_card)

    # 1. 序号匹配: "第一个"、"第二个"、"第1个"
    ordinal_map = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    for word in sorted(ordinal_map.keys(), key=len, reverse=True):
        if word in query:
            idx = ordinal_map[word]
            if product_cards and idx <= len(product_cards):
                card = product_cards[idx - 1]
                return _product_from_card(card)

    # 2. 按商品名匹配 product_cards（标题前几个字出现在 query 中）
    if product_cards:
        for card in product_cards:
            title = card.get("title", "")
            if title and len(title) >= 3 and title[:4] in query:
                return _product_from_card(card)

    # 3. Qdrant 搜索：从 "加入购物车" 前的文本提取搜索词
    for marker in ["加入购物车", "加到购物车", "加购", "添加到购物车"]:
        if marker in query:
            prefix = query.split(marker)[0].strip()
            # 去掉 "把" "将" 等引导词
            for lead in ["把", "将", "这个", "这款", "那个"]:
                if prefix.startswith(lead):
                    prefix = prefix[len(lead):].strip()
            if prefix and len(prefix) >= 2:
                try:
                    from app.services.rag import retrieve as rag_retrieve
                    result = await rag_retrieve(query=prefix, top_k=1)
                    chunks = result.get("chunks", [])
                    if chunks:
                        p = chunks[0].get("payload", {})
                        pid = str(p.get("product_id", "")).strip()
                        if pid:
                            return {
                                "id": pid,
                                "title": p.get("title", ""),
                                "price": p.get("price", 0),
                            }
                except Exception as e:
                    logger.warning("Cart Qdrant fallback lookup failed: %s", e)
            break

    return None


async def _remove_from_cart(query: str, session_id: str, db, user_id: str = "") -> str:
    """从购物车中删除商品，按序号或名字匹配"""
    items = await cart_service.get_cart(db, session_id, user_id=user_id)
    if not items:
        return "购物车是空的，没有可删除的商品。"

    item_index, index_error = _extract_cart_item_index(query, len(items))
    if index_error:
        return index_error
    if item_index is not None:
        item = items[item_index]
        await cart_service.remove_from_cart(db, session_id, str(item.product_id), user_id=user_id)
        return f"✅ 已从购物车删除「{item.title}」。"

    # 2. 按商品名匹配
    for item in items:
        if _cart_item_matches_query(item, query):
            await cart_service.remove_from_cart(db, session_id, str(item.product_id), user_id=user_id)
            return f"✅ 已从购物车删除「{item.title}」。"

    return f"没有找到要删除的商品。当前购物车有 {len(items)} 件商品，请指定序号或商品名。"


async def _update_cart_quantity(query: str, session_id: str, db, user_id: str = "") -> str:
    """按序号或商品名修改购物车数量。"""
    quantity = _parse_quantity(query)
    quantity_delta = _parse_quantity_delta(query)
    if quantity_delta is not None:
        quantity = None
    if quantity is None and quantity_delta is None:
        return "请告诉我想改成几件，例如「把第一个数量改成 2」或「把蓝牙耳机加一件」。"

    items = await cart_service.get_cart(db, session_id, user_id=user_id)
    if not items:
        return "购物车是空的，暂时没有可修改数量的商品。"

    target_indices, indices_error = _extract_cart_item_indices(query, len(items))
    if indices_error:
        return indices_error
    targets = [items[idx] for idx in target_indices]

    if not targets:
        for item in items:
            if _cart_item_matches_query(item, query):
                targets = [item]
                break

    if not targets:
        return "没有找到要修改数量的商品，请指定序号或商品名。"

    changed: list[str] = []
    removed: list[str] = []
    for target in targets:
        new_quantity = quantity
        if new_quantity is None and quantity_delta is not None:
            new_quantity = max(0, target.quantity + quantity_delta)

        if new_quantity == 0:
            await cart_service.remove_from_cart(db, session_id, str(target.product_id), user_id=user_id)
            removed.append(target.title)
        else:
            await cart_service.update_quantity(db, session_id, str(target.product_id), new_quantity, user_id=user_id)
            changed.append(f"「{target.title}」数量改为 {new_quantity} 件")

    messages = []
    if changed:
        messages.append("已将" + "，".join(changed))
    if removed:
        messages.append("已将" + "、".join(f"「{title}」" for title in removed) + "从购物车移除")
    return "；".join(messages) + "。"


# ── Cart Node ──

async def node_cart(state: "AgentState") -> "AgentState":
    """购物车操作节点：调用 cart_service.py 执行 CRUD"""
    query = state["query"]
    conversation_session_id = state.get("session_id", "")
    session_id = state.get("cart_session_id") or conversation_session_id
    user_id = state.get("user_id", "") or ""

    # 确定 cart_action
    cart_action = _extract_cart_action(query)
    state["cart_action"] = cart_action
    logger.info(
        "Cart node: action=%s, cart_session=%s, user=%s",
        cart_action,
        session_id[:8] if session_id else "none",
        user_id[:12] if user_id else "anon",
    )

    if not session_id:
        state["response"] = "会话未初始化，无法操作购物车。请刷新页面重试。"
        state["product_cards"] = []
        return state

    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            if cart_action == "view":
                items = await cart_service.get_cart(db, session_id, user_id=user_id)
                total = await cart_service.get_cart_total(db, session_id, user_id=user_id)
                if items:
                    item_lines = [f"{i+1}. {it.title} ×{it.quantity}  ¥{it.price:.0f}"
                                  for i, it in enumerate(items)]
                    state["response"] = (
                        f"🛒 购物车（{len(items)}件，合计 ¥{total:.0f}）：\n"
                        + "\n".join(item_lines)
                        + "\n\n输入「删除第N个」可移除商品，「清空购物车」可清空，「下单」可结算。"
                    )
                else:
                    state["response"] = "购物车是空的。请先搜索商品，然后说「把第一个加入购物车」来添加。"
                state["product_cards"] = []

            elif cart_action == "add":
                products = _find_products_for_multi_cart(query, state)
                product = None if products else await _find_product_for_cart(query, state)
                if products:
                    requested_quantity = _parse_quantity(query) or 1
                    for product_item in products:
                        await cart_service.add_to_cart(
                            db, session_id,
                            product_item["id"], product_item["title"], product_item["price"],
                            user_id=user_id,
                        )
                        if requested_quantity > 1:
                            await cart_service.update_quantity(
                                db, session_id, product_item["id"], requested_quantity, user_id=user_id
                            )
                    items = await cart_service.get_cart(db, session_id, user_id=user_id)
                    total = await cart_service.get_cart_total(db, session_id, user_id=user_id)
                    names = "、".join(f"「{item['title']}」" for item in products[:3])
                    suffix = "等" if len(products) > 3 else ""
                    state["response"] = (
                        f"✅ 已将{names}{suffix}共 {len(products)} 款商品加入购物车。\n"
                        f"当前购物车共 {len(items)} 件，合计 ¥{total:.0f}。"
                    )
                    await db.commit()
                elif product and product.get("id"):
                    requested_quantity = _parse_quantity(query) or 1
                    await cart_service.add_to_cart(
                        db, session_id,
                        product["id"], product["title"], product["price"],
                        user_id=user_id,
                    )
                    if requested_quantity > 1:
                        await cart_service.update_quantity(
                            db, session_id, product["id"], requested_quantity, user_id=user_id
                        )
                    items = await cart_service.get_cart(db, session_id, user_id=user_id)
                    total = await cart_service.get_cart_total(db, session_id, user_id=user_id)
                    state["response"] = (
                        f"✅ 已将「{product['title']}」(¥{product['price']:.0f}) 加入购物车。\n"
                        f"当前购物车共 {len(items)} 件，合计 ¥{total:.0f}。"
                    )
                    await db.commit()
                else:
                    state["response"] = (
                        "抱歉，没有找到要添加的商品。请先搜索商品（如「推荐蓝牙耳机」），"
                        "然后说「把第一个加入购物车」来添加。"
                    )
                state["product_cards"] = []

            elif cart_action == "quantity":
                state["response"] = await _update_cart_quantity(query, session_id, db, user_id=user_id)
                await db.commit()
                state["product_cards"] = []

            elif cart_action == "remove":
                state["response"] = await _remove_from_cart(query, session_id, db, user_id=user_id)
                await db.commit()
                state["product_cards"] = []

            elif cart_action == "clear":
                await cart_service.clear_cart(db, session_id, user_id=user_id)
                await db.commit()
                state["response"] = "🗑️ 购物车已清空。"
                state["product_cards"] = []

            elif cart_action == "checkout":
                items = await cart_service.get_cart(db, session_id, user_id=user_id)
                total = await cart_service.get_cart_total(db, session_id, user_id=user_id)
                if not items:
                    state["response"] = "购物车是空的，无法下单。请先添加商品。"
                    state["product_cards"] = []
                    return state

                # 判断是"查看订单"还是"确认下单"
                is_confirm = any(kw in query for kw in ["确认下单", "确认", "是的", "确定", "没错"])
                if is_confirm:
                    state["response"] = (
                        "正在为你打开确认下单页面，请在页面核对商品、收货地址和金额后提交订单。"
                    )
                else:
                    item_lines = [f"{i+1}. {it.title} ×{it.quantity} — ¥{it.price * it.quantity:.0f}"
                                  for i, it in enumerate(items)]
                    state["response"] = (
                        "📋 订单确认：\n" + "\n".join(item_lines)
                        + f"\n\n💰 合计：¥{total:.0f}\n\n"
                        + "输入「确认下单」完成购买（演示环境，不会实际扣款）。"
                    )
                state["product_cards"] = []

    except Exception as e:
        logger.error("Cart operation failed: %s", e)
        state["response"] = "购物车操作失败，请稍后重试"
        state["product_cards"] = []

    return state


async def node_web_search(state: AgentState) -> AgentState:
    """联网搜索节点 — DuckDuckGo 搜索 + LLM 知识兜底"""
    query = state.get("rewritten_query") or state.get("query", "")
    try:
        results = await search_web(query)
        if results:
            formatted = format_search_results(results)
            prompt = WEB_SEARCH_PROMPT.format(query=query, search_results=formatted)
            from app.services.llm_client import chat_completion as cc
            response = await cc(messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300, stream=False)
            state["response"] = response
            state["_web_results"] = results
            state["_is_fallback"] = False
        else:
            # DuckDuckGo 不可用，使用 LLM 训练知识兜底
            logger.info("Web search returned 0 results, using LLM knowledge fallback")
            prompt = WEB_SEARCH_FALLBACK_PROMPT.format(query=query)
            from app.services.llm_client import chat_completion as cc
            response = await cc(messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300, stream=False)
            state["response"] = response
            state["_web_results"] = []
            state["_is_fallback"] = True
    except Exception as e:
        logger.warning("Web search node failed: %s", e)
        # 最底层兜底
        prompt = WEB_SEARCH_FALLBACK_PROMPT.format(query=query)
        try:
            from app.services.llm_client import chat_completion as cc
            response = await cc(messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=200, stream=False)
            state["response"] = response
        except Exception:
            state["response"] = "抱歉，联网搜索暂时不可用。你可以试试在本地商品库中搜索具体的商品需求。"
        state["_web_results"] = []
        state["_is_fallback"] = True
    state["product_cards"] = []
    return state


async def _resolve_compare_targets(query: str, conversation_id: str, history: list) -> list[str] | None:
    """检测回指：用户是否引用了上一轮推荐中的某几款商品进行对比。

    支持模式：
    - "对比前两款"、"比较前两个" → 取前2个
    - "对比第1和第3款"、"比较第2个和第3个" → 取指定索引
    - "对比这两款"、"比较那俩" → 取前2个（从上一轮）
    - "对比XM5和QC45" → 不处理（名称匹配走检索），返回None
    """
    import re

    if not history or len(history) < 2:
        return None

    q = query.strip()

    # 检测回指关键词
    backref_keywords = ["前两", "前2", "前二", "这两", "那两", "前几", "这俩", "那俩",
                        "第一款", "第二款", "第三款", "第1款", "第2款", "第3款",
                        "第.和第", "第.跟第", "第.与第",
                        "上面", "刚才", "刚刚", "前面推荐"]

    has_backref = any(kw in q for kw in backref_keywords)

    # 也匹配 "对比第1和第3" 这种数字模式
    index_pattern = re.findall(r'第\s*(\d+)\s*(?:款|个)', q)
    if not has_backref and not index_pattern:
        return None

    # 从状态管理器获取上一轮 product_cards
    from app.services import state_manager as sm
    prev_state = await sm.get_state(conversation_id)
    prev_cards = prev_state.get("product_cards", []) if prev_state else []

    if not prev_cards or len(prev_cards) < 2:
        logger.info("Compare backref: no previous product_cards to resolve from")
        return None

    logger.info("Compare backref: query='%s', prev_cards=%d", q[:40], len(prev_cards))

    # 提取用户指定的索引
    if index_pattern:
        indices = [int(i) - 1 for i in index_pattern]  # 转为0-based
    elif any(kw in q for kw in ["前两", "前2", "前二", "这两", "那两", "这俩", "那俩"]):
        indices = [0, 1]  # 默认前2款
    else:
        indices = [0, 1]  # 兜底：前2款

    # 过滤有效索引
    valid_indices = [i for i in indices if 0 <= i < len(prev_cards)]
    if len(valid_indices) < 2:
        return None

    target_ids = [prev_cards[i].get("product_id", "") for i in valid_indices]
    target_ids = [pid for pid in target_ids if pid]

    if len(target_ids) >= 2:
        logger.info("Compare backref resolved: indices=%s → ids=%s", valid_indices, target_ids)
        return target_ids

    return None


def _detect_compare_brands(query: str, products: list[dict]) -> list[str]:
    """从查询中检测用户明确提到的品牌，返回匹配到的品牌名列表（按查询中出现顺序）。

    例如 "对比华为和Apple手机" → ["Huawei", "Apple"]（匹配 products 中实际品牌名）
    未检测到明确品牌时返回空列表。
    """
    import re

    # 从 products 中收集已知品牌（用于大小写/中英文映射）
    known_brands = {}
    for p in products:
        b = (p.get("brand") or "").strip()
        if b:
            known_brands[b.lower()] = b

    if len(known_brands) < 2:
        return []

    # 构建品牌名关键词列表，按长度降序避免短词误匹配（如 "小米" 不应仅匹配 "米"）
    brand_keys = sorted(known_brands.keys(), key=len, reverse=True)

    # 在 query 中查找品牌名出现的位置和对应的标准品牌名
    found: list[tuple[int, str]] = []  # (position, canonical_brand)
    q_lower = query.lower()

    for key in brand_keys:
        pos = q_lower.find(key)
        if pos >= 0:
            # 排除品牌名是常见词的误匹配（如 "小米" 不在 "对比" 中）
            found.append((pos, known_brands[key]))

    # 按位置排序，去重
    found.sort()
    result = []
    seen = set()
    for _, brand in found:
        if brand.lower() not in seen:
            result.append(brand)
            seen.add(brand.lower())

    return result[:3]  # 最多3个品牌


async def node_compare(state: AgentState) -> AgentState:
    """商品对比节点 — 从检索结果中取 top 2-3 商品，调用 comparator 生成多维度对比。
    支持 _target_product_ids 跳过检索直接对比指定商品。
    """
    from app.services.comparator import compare_products as run_comparison
    from app.services.product_ranker import rank_products

    query = state.get("rewritten_query") or state.get("query", "")
    slots = state.get("slots", {})
    target_product_ids = state.get("_target_product_ids", [])
    chunks = state.get("retrieved_chunks", [])

    # 使用已解析的目标商品 ID（来自回指解析）或从检索结果中取 top-N
    if target_product_ids and len(target_product_ids) >= 2:
        product_ids = target_product_ids
        # 从缓存/检索结果中获取商品详情
        raw_products = _extract_raw_products(chunks) if chunks else []
        if not raw_products:
            # 需要从 Qdrant fetch 这些产品的 payload
            from app.services.comparator import _fetch_products_from_qdrant
            raw_products = await _fetch_products_from_qdrant(product_ids)
        ranked = list(raw_products)  # 保持原始顺序
        logger.info("node_compare: using resolved target IDs: %s", product_ids)
    else:
        if not chunks:
            logger.warning("node_compare: no retrieved chunks, falling back to text-only")
            state["response"] = "抱歉，没有找到可对比的商品，试试更具体的商品名称吧。"
            state["product_cards"] = []
            return state

        raw_products = _extract_raw_products(chunks)
        user_prefs = _build_user_prefs(slots)
        ranked = rank_products(raw_products, user_prefs, "commodity_compare", top_k=3)

        if len(ranked) < 2:
            state["response"] = "需要至少 2 个商品才能进行对比。试试提供更具体的商品名称。"
            state["product_cards"] = []
            return state

        # 用户明确提了N个品牌 → 每个品牌只取最优的1款，避免多选
        query_brands = _detect_compare_brands(query, ranked)
        if query_brands and len(query_brands) == 2:
            brand_picks = []
            for brand in query_brands:
                match = next((r for r in ranked if (r.get("brand") or "").lower() == brand.lower()), None)
                if match:
                    brand_picks.append(match)
            if len(brand_picks) == 2:
                ranked = brand_picks
                logger.info("node_compare: brand-filtered to 2: %s", [r.get("brand") for r in ranked])

        product_ids = [r["product_id"] for r in ranked]

    logger.info("node_compare: comparing %d products: %s", len(product_ids), product_ids)

    try:
        comparison = await run_comparison(product_ids=product_ids, dimensions=None)
    except Exception as e:
        logger.error("node_compare: comparison failed: %s", e)
        state["response"] = "对比分析暂时不可用，请稍后再试。"
        state["product_cards"] = []
        return state

    # 构建对比文本（无 markdown，纯文本格式）
    dims = comparison.get("dimensions", [])
    summary = comparison.get("summary", "")

    # 构建 products_map：优先用 ranked，否则从 raw_products 构建
    if not target_product_ids:
        products_map = {r["product_id"]: r for r in ranked}
    else:
        products_map = {p.get("product_id", ""): p for p in raw_products}

    lines = ["📊 商品对比"]
    for dim in dims:
        dim_name = dim['name']
        lines.append(f"\n▎{dim_name}")
        for pid, val in dim.get("values", {}).items():
            product = products_map.get(pid, {})
            name = product.get("title", pid)
            # 截短产品名以提高可读性
            short_name = _shorten_product_name(name)
            marker = " 🏆" if dim.get("winner") == pid else ""
            lines.append(f"  {short_name}: {val}{marker}")

    if summary:
        lines.append(f"\n💡 {summary}")

    response_text = "\n".join(lines)
    state["response"] = response_text

    # 构建 product_cards 供客户端展示
    cards = []
    products_for_cards = ranked if not target_product_ids else raw_products
    for i, p in enumerate(products_for_cards):
        if isinstance(p, str):
            # 原始 product_id，从 products_map 取
            p = products_map.get(p, {})
        cards.append({
            "product_id": p.get("product_id", ""),
            "title": p.get("title", ""),
            "price": float(p.get("price", 0)),
            "rating": float(p.get("rating", 3.0)),
            "highlights": (p.get("highlights") or [])[:3] if isinstance(p.get("highlights"), list) else [],
            "image_url": (p.get("image_urls") or [None])[0] if p.get("image_urls") else None,
            "image_urls": p.get("image_urls") if isinstance(p.get("image_urls"), list) else [],
            "brand": p.get("brand", ""),
            "category": p.get("category", ""),
        })
    state["product_cards"] = cards
    state["_comparison_dims"] = dims  # 暂存维度数据，供 SSE 发射

    return state


# ── Router ──

def route_after_intent(state: AgentState) -> str:
    """意图路由：闲聊 → generate, 联网搜索 → web_search, 对比 → compare, 缺失信息 → clarify, 购物车 → cart, 其他 → retrieve"""
    if state.get("intent") == "chitchat":
        return "generate"

    if state.get("intent") == "web_search":
        return "web_search"

    if state.get("intent") == "commodity_compare":
        return "compare"

    if state.get("intent") == "cart_operation":
        return "cart"

    slots = state.get("slots", {})
    missing = slots.get("missing_slots", [])
    has_category = bool(slots.get("category"))
    has_scenario = bool(slots.get("scenario"))
    has_budget = bool(slots.get("price_min") or slots.get("price_max"))
    has_attrs = bool(slots.get("attributes"))
    confidence = state.get("confidence", 0.5)
    intent_type = state.get("intent", "")
    original_query = state.get("query", "").strip()

    ultra_vague_words = {"推荐", "买东西", "推荐一下", "买什么", "买啥", "有什么", "推荐个"}
    is_ultra_vague = len(original_query) <= 3 or original_query in ultra_vague_words

    missing_everything = bool(missing) and not (has_category or has_scenario or has_budget or has_attrs)
    only_has_category = has_category and not (has_scenario or has_budget or has_attrs)
    # 含显式推荐/搜索关键词的短查询（如"推荐手机"、"耳机的推荐"）不应追问
    has_explicit_intent = any(kw in original_query for kw in ("推荐", "找", "买", "搜", "选购"))
    short_category_only = len(original_query) <= 4 and only_has_category and not has_explicit_intent
    low_confidence = confidence < 0.5 and intent_type == "commodity_recommend"

    # 非购物意图不追问（闲聊、反选、购物车、对比）
    non_shopping_intents = {"chitchat", "anti_selection", "cart_operation", "commodity_compare"}
    needs_clarify = (is_ultra_vague or missing_everything or short_category_only or low_confidence) \
        and intent_type not in non_shopping_intents

    # 有多轮历史时，短查询是在之前推荐基础上的细化（如"要轻量的"），跳过追问
    conversation_history = state.get("history", [])
    is_short_query = len(original_query) <= 4
    if needs_clarify and len(conversation_history) >= 2 and (is_short_query or is_ultra_vague):
        logger.info("Clarify bypassed due to conversation history")
        needs_clarify = False

    if needs_clarify:
        return "clarify"

    return "retrieve"


# ── Graph Builder ──

def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("classify_intent", node_classify_intent)
    workflow.add_node("clarify", node_clarify)
    workflow.add_node("retrieve", node_retrieve)
    workflow.add_node("compare", node_compare)
    workflow.add_node("cart", node_cart)
    workflow.add_node("web_search", node_web_search)
    workflow.add_node("generate", node_generate)

    workflow.set_entry_point("classify_intent")
    workflow.add_conditional_edges("classify_intent", route_after_intent, {
        "retrieve": "retrieve",
        "clarify": "clarify",
        "compare": "compare",
        "cart": "cart",
        "web_search": "web_search",
        "generate": "generate",
    })
    workflow.add_edge("clarify", "generate")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("compare", "generate")
    workflow.add_edge("cart", "generate")
    workflow.add_edge("web_search", "generate")
    workflow.add_edge("generate", END)

    return workflow


agent_graph = build_agent_graph().compile()


async def run_agent(query: str, session_id: str = "") -> dict:
    """
    内部评测入口 — 运行完整 Agent 图并返回最终状态。
    供 evaluator.py 等内部模块调用，不走 HTTP/SSE。
    """
    initial_state: AgentState = {
        "query": query,
        "session_id": session_id,
        "slots": {},
    }
    final_state = await agent_graph.ainvoke(initial_state)
    return final_state


def _safe_emit_boundary(unemitted: str) -> int:
    """返回 unemitted 中可以安全输出的位置 — 保留最后一句完整句子用于三特征检测。"""
    if len(unemitted) < 40:
        return 0
    boundaries = []
    for sep in ("。", "！", "？"):
        pos = -1
        while True:
            pos = unemitted.find(sep, pos + 1)
            if pos < 0:
                break
            boundaries.append(pos + 1)  # 包含标点
    if len(boundaries) < 2:
        return 0
    boundaries.sort()
    return boundaries[-2]  # 保留最后一句，输出倒数第二句之前的所有内容


async def _stream_interleaved(stream, cards: list) -> AsyncGenerator:
    """真流式交错输出 — 逐 token 发送文字，边收边检测卡片插入点。

    检测策略：
    1. 「商品N」标记扫描 — 最精确，立即在标记处插入卡片
    2. 三特征检测 — 匹配依据/品质亮点/适用场景 全部出现在第N款商品时，
       等待适用场景句号到达后插入第N张卡片
    3. 安全输出：只输出倒数第二句号之前的文本，保留最后一句在缓冲区中
       以确保卡片边界检测能完整捕获"适用场景。"的句号。
    """
    buffer = ""           # 全部已接收文本
    emitted_pos = 0       # 已发送到客户端的缓冲位置
    emitted_indices = set()
    closing_seen = False

    marker_re = re.compile(r"「商品\s*(\d+)\s*」|\[PRODUCT_(\d+)\]|【PRODUCT_(\d+)】")
    tag_re = re.compile(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", re.IGNORECASE)
    closing_re = re.compile(r"「结语」|\[CLOSING\]|【CLOSING】", re.IGNORECASE)

    def _card(idx: int):
        if idx >= len(cards):
            return None
        c = cards[idx]
        return {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=c.get("product_id", c.get("id", "")),
                title=c.get("title", ""), price=c.get("price", 0),
                rating=c.get("rating", 0),
                match_score=c.get("match_score", c.get("score", 0.5)),
                highlights=c.get("highlights", []),
                image_url=c.get("image_url"), image_urls=c.get("image_urls", []),
                brand=c.get("brand"), category=c.get("category", ""),
                index=idx + 1, total=len(cards),
            ).model_dump_json(),
        }

    def _emit_up_to(pos: int):
        """输出 emitted_pos 到 pos 之间的文本（清理标记后）。"""
        nonlocal emitted_pos
        if pos <= emitted_pos:
            return
        seg = buffer[emitted_pos:pos]
        clean = tag_re.sub("", seg)
        if clean.strip():
            yield_me = {"event": "text_delta", "data": TextDeltaEvent(content=clean).model_dump_json()}
            emitted_pos = pos
            return yield_me
        emitted_pos = pos
        return None

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if not delta.content:
            continue

        buffer += delta.content

        # ── Closing 之后：直接透传 ──
        if closing_seen:
            evt = _emit_up_to(len(buffer))
            if evt:
                yield evt
            continue

        # ── Closing 检测 ──
        cm = closing_re.search(buffer, emitted_pos)
        if cm:
            evt = _emit_up_to(cm.start())
            if evt:
                yield evt
            next_idx = len(emitted_indices)
            if next_idx < len(cards):
                ce = _card(next_idx)
                if ce:
                    emitted_indices.add(next_idx)
                    yield ce
            emitted_pos = cm.end()
            closing_seen = True
            continue

        # ── 策略1: 「商品N」标记 ──
        # 标记表示下一款商品的开头，不是当前卡片的插入点。
        # 因此在「商品2」处发送商品1卡片，在「商品3」处发送商品2卡片。
        m = marker_re.search(buffer, emitted_pos)
        if m:
            evt = _emit_up_to(m.start())
            if evt:
                yield evt
            card_num = int(m.group(1) or m.group(2) or m.group(3))
            prev_idx = card_num - 2
            if 0 <= prev_idx < len(cards) and prev_idx not in emitted_indices:
                ce = _card(prev_idx)
                if ce:
                    emitted_indices.add(prev_idx)
                    yield ce
            elif card_num > 1:
                next_idx = len(emitted_indices)
                if next_idx < min(card_num - 1, len(cards)):
                    ce = _card(next_idx)
                    if ce:
                        emitted_indices.add(next_idx)
                        yield ce
            emitted_pos = m.end()
            continue

        # ── 策略2: 三特征检测（匹配依据 + 品质亮点 + 适用场景） ──
        count_a = buffer.count("匹配依据")
        count_b = buffer.count("品质亮点")
        count_c = buffer.count("适用场景")
        min_count = min(count_a, count_b, count_c)

        while min_count > len(emitted_indices):
            # 找到第 len(emitted_indices)+1 次"适用场景"后的句号位置
            target = len(emitted_indices) + 1
            nth = _nth_occurrence(buffer, "适用场景", target)
            end = buffer.find("。", nth)
            if end < 0:
                break  # 句号还没到，继续等

            card_pos = end + 1  # 卡片插在句号之后
            evt = _emit_up_to(card_pos)
            if evt:
                yield evt

            # 按顺序发下一张未发送的卡片
            next_idx = len(emitted_indices)
            if next_idx < len(cards):
                ce = _card(next_idx)
                if ce:
                    emitted_indices.add(next_idx)
                    yield ce
            else:
                break

        # ── 安全输出：只发倒数第二句号之前的文本，保留最后一句在缓冲中 ──
        unemitted = buffer[emitted_pos:]
        safe = _safe_emit_boundary(unemitted)
        if safe > 0:
            evt = _emit_up_to(emitted_pos + safe)
            if evt:
                yield evt

    # ── 流结束：输出剩余文本 + 兜底卡片 ──
    evt = _emit_up_to(len(buffer))
    if evt:
        yield evt

    for idx in range(len(cards)):
        if idx not in emitted_indices:
            ce = _card(idx)
            if ce:
                yield ce


def _find_card_boundaries(text: str, cards: list) -> list:
    """在完整响应文本中定位每张卡片的插入点，返回 [(position, card_idx), ...] 按位置排序。

    策略优先级：
    1. 「商品N」标记 — 最精确
    2. 三特征检测（匹配依据 + 品质亮点 + 适用场景）— LLM 几乎一定会输出
    3. 标题模糊匹配 — 兜底
    """
    marker_re = re.compile(r"「商品\s*(\d+)\s*」|\[PRODUCT_(\d+)\]|【PRODUCT_(\d+)】")

    # 策略1: 标记
    # 「商品N」是第 N 款商品详情的开头。卡片应出现在上一款详情文本之后：
    # 「商品2」前插商品1卡，「商品3」前插商品2卡，最后一款放在正文末尾。
    boundaries = []
    marker_matches = list(marker_re.finditer(text))
    for m in marker_matches:
        card_num = int(m.group(1) or m.group(2) or m.group(3))
        card_idx = card_num - 2
        if 0 <= card_idx < len(cards):
            boundaries.append((m.start(), card_idx))
    if marker_matches:
        last_card_num = int(marker_matches[-1].group(1) or marker_matches[-1].group(2) or marker_matches[-1].group(3))
        last_card_idx = last_card_num - 1
        if 0 <= last_card_idx < len(cards):
            boundaries.append((len(text), last_card_idx))
    if boundaries:
        boundaries.sort(key=lambda x: x[0])
        return boundaries

    # 策略2: 三特征检测 — 匹配依据、品质亮点、适用场景 同时出现第N次 → 第N张卡片
    # 卡片放在适用场景段落末尾（句号之后）
    for card_idx in range(len(cards)):
        target = card_idx + 1
        pos_a = _nth_occurrence(text, "匹配依据", target)
        pos_b = _nth_occurrence(text, "品质亮点", target)
        pos_c = _nth_occurrence(text, "适用场景", target)
        if pos_a < 0 or pos_b < 0 or pos_c < 0:
            break
        # 卡片插入点：适用场景后第一个句号之后
        end = text.find("。", pos_c)
        if end >= 0:
            boundaries.append((end + 1, card_idx))
        else:
            boundaries.append((pos_c + 4, card_idx))  # len("适用场景") = 4

    if boundaries:
        boundaries.sort(key=lambda x: x[0])
        return boundaries

    # 策略3: 标题模糊匹配
    for card_idx, card in enumerate(cards):
        title = card.get("title", "").strip()
        if not title or len(title) < 3:
            continue
        pos = text.find(title)
        if pos < 0:
            tokens = re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', title)
            if len(tokens) >= 2:
                for start in range(1, min(3, len(tokens))):
                    sub = ''.join(tokens[start:])
                    if len(sub) >= 4:
                        pos = text.find(sub)
                        if pos >= 0:
                            break
        if pos < 0:
            prefix = title[:6].strip()
            if len(prefix) >= 4:
                pos = text.find(prefix)
        if pos >= 0:
            boundaries.append((pos, card_idx))

    boundaries.sort(key=lambda x: x[0])
    return boundaries


def _nth_occurrence(text: str, pattern: str, n: int) -> int:
    """返回 pattern 在 text 中第 n 次出现的位置（0-indexed），未找到返回 -1。"""
    pos = -1
    for _ in range(n):
        pos = text.find(pattern, pos + 1)
        if pos == -1:
            return -1
    return pos


async def _emit_interleaved(response_text: str, cards: list) -> AsyncGenerator:
    """基于完整文本的交错输出：文本分段 → 清理标记 → 16字符分块输出 → 插入卡片。

    卡片位置由 _find_card_boundaries 预计算，基于完整文本，定位准确。
    """
    tag_re = re.compile(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", re.IGNORECASE)
    closing_re = re.compile(r"「结语」|\[CLOSING\]|【CLOSING】", re.IGNORECASE)

    def _card(idx: int) -> dict:
        if idx >= len(cards):
            return None
        c = cards[idx]
        return {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=c.get("product_id", c.get("id", "")),
                title=c.get("title", ""), price=c.get("price", 0),
                rating=c.get("rating", 0),
                match_score=c.get("match_score", c.get("score", 0.5)),
                highlights=c.get("highlights", []),
                image_url=c.get("image_url"), image_urls=c.get("image_urls", []),
                brand=c.get("brand"), category=c.get("category", ""),
                index=idx + 1, total=len(cards),
            ).model_dump_json(),
        }

    # 1. 分离结语：结语标记之后的内容不再插入卡片
    body_text = response_text
    closing_text = ""
    cm_body = closing_re.search(response_text)
    if cm_body:
        body_text = response_text[: cm_body.start()]
        closing_text = response_text[cm_body.start():]

    # 2. 找到每张卡片的插入点
    boundaries = _find_card_boundaries(body_text, cards)

    # 3. 按卡片边界切分文本 → 逐段输出文本 + 卡片
    emitted = set()
    prev_pos = 0
    for pos, card_idx in boundaries:
        if card_idx in emitted:
            continue
        seg_text = tag_re.sub("", body_text[prev_pos:pos])
        # 输出文本
        for i in range(0, len(seg_text), 16):
            chunk = seg_text[i : i + 16]
            if chunk:
                yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}
        # 输出卡片
        evt = _card(card_idx)
        if evt:
            emitted.add(card_idx)
            yield evt
        prev_pos = pos

    # 4. 剩余正文文本（卡片之后、结语之前）
    remaining_body = tag_re.sub("", body_text[prev_pos:])
    for i in range(0, len(remaining_body), 16):
        chunk = remaining_body[i : i + 16]
        if chunk:
            yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}

    # 5. 结语文本
    closing_text = tag_re.sub("", closing_text)
    for i in range(0, len(closing_text), 16):
        chunk = closing_text[i : i + 16]
        if chunk:
            yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}

    # 6. 兜底：未发送的卡片附在末尾
    for idx in range(len(cards)):
        if idx not in emitted:
            evt = _card(idx)
            if evt:
                yield evt


def _build_cache_key(message: str, conversation_id: str | None, history: list[dict]) -> str:
    """Build a context-aware cache key so short multi-turn replies do not collide."""
    recent = [
        {"role": h.get("role", ""), "content": (h.get("content", "") or "")[:200]}
        for h in history[-4:]
    ]
    return json.dumps(
        {
            "v": cache.CACHE_VERSION,
            "conversation_id": conversation_id or "",
            "message": message.strip(),
            "history": recent,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


async def _persist_dialog_context(
    conversation_id: str | None,
    state: dict,
    *,
    product_cards: list | None = None,
    intent: str | None = None,
) -> None:
    if not conversation_id:
        return

    slots = state.get("slots", {}) or {}
    category_context = _update_category_context(state.get("category_context", {}), slots)
    state["category_context"] = category_context

    update_kwargs = {
        "slots": slots,
        "category_context": category_context,
        "intent": intent or state.get("intent", ""),
    }
    if product_cards is not None:
        update_kwargs["product_cards"] = product_cards
    elif state.get("_category_changed"):
        update_kwargs["product_cards"] = []

    try:
        await sm.update_state(conversation_id, **update_kwargs)
    except Exception as e:
        logger.warning("State update failed for conversation '%s': %s", conversation_id, e)


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


def _clean_stream_text(text: str) -> str:
    """Remove internal structure markers before streaming text to the client."""
    text = re.sub(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", "", text, flags=re.IGNORECASE)
    return text


async def generate_response(
    message: str,
    conversation_id: str | None = None,
    state: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Agent 真流式响应入口 — 被 api/chat.py 调用。

    架构（v2.0 真流式）：
    1. 缓存检查
    2. 意图分类 + 检索（非流式，~0.8s）
    3. LLM 边生成边推送 text_delta（真流式，TTFT ~1s DeepSeek / ~5s Doubao）
    4. 商品卡片 product_cards
    5. done

    SSE 事件格式:
    - text_delta: 流式文本增量（逐 token）
    - product_cards: 单张推荐商品卡片
    - done: 流结束
    - error: 错误
    """
    t_start = time.monotonic()
    try:
        # Demo 模式快速路径 — 跳过 LLM，仅 Qdrant 检索 + 模板化回复
        if settings.DEMO_MODE:
            from app.services import rag as _rag_module
            logger.info("DEMO_MODE: mock SSE for query=%s", message[:60])
            yield {"event": "progress", "data": ProgressEvent(message="[演示模式] 正在检索商品...").model_dump_json()}
            result = await _rag_module.retrieve(query=message, top_k=settings.RETRIEVAL_TOP_K)
            chunks = result.get("chunks", [])
            if chunks:
                yield {"event": "text_delta", "data": TextDeltaEvent(content=f"[演示模式] 为您找到 {len(chunks[:5])} 款相关商品：\n\n").model_dump_json()}
                total = min(len(chunks), 5)
                for i, c in enumerate(chunks[:total]):
                    p = c.get("payload", {})
                    yield {"event": "product_cards", "data": ProductCardEvent(
                        product_id=p.get("product_id", ""),
                        title=p.get("title", ""),
                        price=p.get("price", 0),
                        rating=p.get("rating", 0),
                        image_url=p.get("image_url") or (p.get("image_urls", [None])[0] if p.get("image_urls") else None),
                        category=p.get("category", ""),
                        highlights=p.get("highlights", [])[:3],
                        match_score=round(c.get("score", 0.5), 4),
                        index=i + 1,
                        total=total,
                    ).model_dump_json()}
            else:
                yield {"event": "text_delta", "data": TextDeltaEvent(content="[演示模式] 未找到匹配商品，请尝试其他关键词。\n").model_dump_json()}
            yield {"event": "done", "data": DoneEvent(latency_ms=0, total_cards=min(len(chunks), 5), message="demo-mode").model_dump_json()}
            return

        yield {"event": "progress", "data": ProgressEvent(message="正在分析您的需求...").model_dump_json()}
        yield {"event": "text_delta", "data": TextDeltaEvent(content="收到，我马上帮你处理。\n\n").model_dump_json()}

        # 获取多轮对话历史。缓存 key 也必须包含上下文，避免“便宜一点”等短句误命中。
        from app.services import state_manager as sm
        conversation_history = await sm.get_recent_messages(conversation_id or "", limit=6)
        cache_key = _build_cache_key(message, conversation_id, conversation_history)

        # ── 缓存检查 ──
        cached = await cache.get(message, cache_key=cache_key)
        if cached:
            response_text = cached["response"]
            cards = cached["cards"]
            # 安全阀：旧缓存可能包含>3件商品，截断至top 3
            if len(cards) > 3:
                cards = cards[:3]
            async for evt in _emit_interleaved(response_text, cards):
                yield evt
            elapsed = (time.monotonic() - t_start) * 1000
            yield {"event": "done", "data": DoneEvent(latency_ms=int(elapsed), message="cache-hit").model_dump_json()}
            return

        # ── 缓存检查 ──
        # 阶段 1: 意图分类 + 检索（非流式，~0.8s）
        # ═══════════════════════════════════════════════════════

        initial_state: AgentState = {
            "query": message,
            "session_id": conversation_id or "",
            "cart_session_id": (state or {}).get("cart_session_id", "") if isinstance(state, dict) else "",
            "user_id": (state or {}).get("user_id", "") if isinstance(state, dict) else "",
            "slots": (state or {}).get("slots", {}) if isinstance(state, dict) else {},
            "category_context": (state or {}).get("category_context", {}) if isinstance(state, dict) else {},
            "product_cards": (state or {}).get("product_cards", []) if isinstance(state, dict) else [],
            "history": conversation_history,
        }

        after_intent = await node_classify_intent(initial_state)
        if after_intent.get("intent") != "chitchat":
            await _persist_dialog_context(conversation_id, after_intent)

        cart_keywords = [
            "购物车", "加购", "加入购物车", "加到购物车", "添加到购物车",
            "删除", "移除", "清空", "数量改", "改成", "改为",
            "设为", "设置为", "调整为", "调到", "改到", "加一件", "减一件",
            "下单", "结算", "结账", "确认下单",
        ]
        if any(kw in message for kw in cart_keywords):
            logger.info("Intent override: cart keyword detected, forcing cart_operation")
            after_intent["intent"] = "cart_operation"

        # 闲聊直接回复
        if after_intent.get("intent") == "chitchat":
            yield {"event": "progress", "data": ProgressEvent(message="已理解您的问题，正在回复...").model_dump_json()}
            text = "你可以告诉我具体的需求，比如「推荐一款降噪耳机」「300元以内的运动鞋」「送女朋友的生日礼物」，我会帮你找到合适的商品～"
            yield {"event": "text_delta", "data": TextDeltaEvent(content=text).model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── 否定/排除语义检测：LLM 可能把 "排除 Apple" 误判为 web_search，
        #     但只要有否定关键词 + 对话历史（多轮上下文），就应走 anti_selection 检索路径
        neg_keywords = ["不要", "除了", "非", "不含", "排除", "拒绝", "去掉", "避开", "别"]
        has_negation_in_query = any(kw in message for kw in neg_keywords)
        has_negation_slots = bool(
            after_intent.get("slots", {}).get("exclude_brands") or
            after_intent.get("slots", {}).get("exclude_categories") or
            after_intent.get("slots", {}).get("exclude_text_terms")
        )
        has_history = len(conversation_history) >= 2
        if after_intent.get("intent") == "web_search" and (has_negation_in_query or has_negation_slots) and has_history:
            logger.info("Overriding web_search → anti_selection: negation detected in multi-turn context")
            after_intent["intent"] = "anti_selection"

        # ── Commerce sanity check: LLM 可能把纯价格/品牌/品类限定词误判为 web_search ──
        #     如 "3000元以下的手表"、"华为手机"、"降噪耳机" — 这些不含"推荐"但明显是导购意图
        if after_intent.get("intent") == "web_search":
            _commerce_keywords = [
                # 价格模式
                r'\d+元', r'\d+块', r'以下', r'以内', r'以上', r'左右', r'以内',
                # 购买意图
                '买', '购', '想搞', '整一个',
                # 品类词（常见电商类目）
                '手机', '耳机', '手表', '电脑', '平板', '相机', '音箱', '键盘', '鼠标',
                '洗面奶', '面霜', '防晒', '精华', '面膜', '口红', '粉底', '化妆',
                '跑鞋', '运动鞋', '篮球鞋', '羽绒服', 'T恤', '卫衣', '背包', '行李箱',
                '降噪', '蓝牙', '无线', '有线', '充电', '续航', '防水', '防摔',
                '推荐', '哪个好', '怎么选', '什么牌子', '性价比',
            ]
            _web_only_keywords = [
                '最新', '新闻', '趋势', '流行', '网上', '搜索', '查一下', '最近有什么',
                '现在什么', '什么时候', '2025', '2026', '今年', '双11', '618', '双十一',
            ]
            _has_commerce = any(
                (re.search(kw, message) if kw.startswith(r'\d') else kw in message)
                for kw in _commerce_keywords
            )
            _has_web_only = any(kw in message for kw in _web_only_keywords)
            if _has_commerce and not _has_web_only:
                logger.info("Overriding web_search → commodity_recommend: commerce keywords detected")
                after_intent["intent"] = "commodity_recommend"
                after_intent["confidence"] = 0.55  # moderate confidence — was overridden

        # ── 联网搜索：外部信息查询 → web_search node → 返回结果 ──
        if after_intent.get("intent") == "web_search":
            yield {"event": "progress", "data": ProgressEvent(message="正在联网搜索...").model_dump_json()}
            after_ws = await node_web_search(after_intent)
            ws_response = after_ws.get("response", "")
            web_results = after_ws.get("_web_results", [])

            # 发送搜索摘要文本
            yield {"event": "text_delta", "data": TextDeltaEvent(content=ws_response).model_dump_json()}

            # 发送每条搜索结果
            for i, wr in enumerate(web_results):
                wr_event = WebSearchResultEvent(
                    title=wr.get("title", ""),
                    url=wr.get("url", ""),
                    snippet=wr.get("snippet", ""),
                    index=i + 1,
                    total=len(web_results),
                )
                yield {"event": "web_search_result", "data": wr_event.model_dump_json()}

            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── 购物车上下文检测：上轮是订单确认页，本轮回复视为确认/取消 ──
        cart_confirm_keywords = {"确认下单", "确认", "是的", "确定", "没错", "下单", "结算"}
        if after_intent.get("intent") != "cart_operation" and conversation_history:
            last_assistant = ""
            for m in reversed(conversation_history):
                if m.get("role") == "assistant":
                    last_assistant = m.get("content", "")
                    break
            if ("订单确认" in last_assistant or "确认下单" in last_assistant) and \
               any(kw in message for kw in cart_confirm_keywords):
                logger.info("Cart context override: detected checkout confirmation reply")
                after_intent["intent"] = "cart_operation"
                after_intent["slots"] = after_intent.get("slots", {})

        # ── 购物车操作：走 cart node → 直接返回，不做 RAG ──
        if after_intent.get("intent") == "cart_operation":
            yield {"event": "progress", "data": ProgressEvent(message="正在处理您的购物车...").model_dump_json()}
            after_cart = await node_cart(after_intent)
            cart_response = after_cart.get("response", "购物车操作完成。")
            yield {"event": "text_delta", "data": TextDeltaEvent(content=cart_response).model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── 商品对比：走 retrieve → compare → 返回结构化对比结果 ──
        if after_intent.get("intent") == "commodity_compare":
            yield {"event": "progress", "data": ProgressEvent(message="正在检索商品，准备对比...").model_dump_json()}

            # 检测回指：用户引用上一轮推荐的某几款（"对比前两款"、"比较第1和第3个"）
            target_ids = await _resolve_compare_targets(
                query=message,
                conversation_id=conversation_id or "",
                history=conversation_history,
            )

            if target_ids and len(target_ids) >= 2:
                logger.info("Compare: using resolved target product_ids: %s", target_ids)
                after_intent["_target_product_ids"] = target_ids
                after_compare = await node_compare(after_intent)
            else:
                after_retrieve = await node_retrieve(after_intent)
                after_compare = await node_compare(after_retrieve)

            compare_response = after_compare.get("response", "")
            compare_cards = after_compare.get("product_cards", [])
            compare_dims = after_compare.get("_comparison_dims", [])

            # 发送对比文本
            if compare_response:
                yield {"event": "text_delta", "data": TextDeltaEvent(content=compare_response).model_dump_json()}

            # 发送对比维度事件
            if compare_dims:
                from app.schemas.sse_events import CompareEvent
                yield {"event": "compare", "data": CompareEvent(dimensions=compare_dims).model_dump_json()}

            # 发送各商品卡片
            for i, card in enumerate(compare_cards):
                card_event = ProductCardEvent(
                    product_id=card.get("product_id", ""),
                    title=card.get("title", ""),
                    price=float(card.get("price", 0)),
                    rating=float(card.get("rating", 3.0)),
                    highlights=card.get("highlights", [])[:3],
                    image_url=card.get("image_url"),
                    image_urls=card.get("image_urls", []),
                    brand=card.get("brand", ""),
                    category=card.get("category", ""),
                    index=i + 1,
                    total=len(compare_cards),
                )
                yield {"event": "product_cards", "data": card_event.model_dump_json()}

            total_ms = int((time.monotonic() - t_start) * 1000)
            yield {"event": "done", "data": DoneEvent(total_cards=len(compare_cards), latency_ms=total_ms).model_dump_json()}
            return

        # ── clarify 反问：由 route_after_intent 统一决策（含历史上下文 + 多场景触发）──
        route = route_after_intent(after_intent)
        if route == "clarify":
            await _persist_dialog_context(conversation_id, after_intent)
            yield {"event": "progress", "data": ProgressEvent(message="正在分析您的需求细节...").model_dump_json()}
            final_state = await agent_graph.ainvoke(after_intent)
            clarify_text = final_state.get("response", "")
            missing_list = after_intent.get("slots", {}).get("missing_slots", [])
            if not isinstance(missing_list, list):
                missing_list = []
            from app.schemas.sse_events import ClarifyEvent
            yield {
                "event": "clarify",
                "data": ClarifyEvent(
                    question=clarify_text or "能再具体说说您的需求吗？",
                    missing_slots=missing_list,
                ).model_dump_json()
            }
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── Progress 2: 意图分类完成，进入检索阶段 ──
        yield {"event": "progress", "data": ProgressEvent(message="已理解需求，正在检索商品...").model_dump_json()}

        after_retrieve = await node_retrieve(after_intent)
        chunks = after_retrieve.get("retrieved_chunks", [])
        slots = after_retrieve.get("slots", {})

        if not chunks:
            if slots.get("category"):
                logger.info("No precise results for '%s', expanding within category=%s", message[:40], slots.get("category"))
                chunks = await _retrieve_same_category_supplements(message, slots, chunks)

        if not chunks and not slots.get("category"):
            # 兜底策略：清除品类 + 排除条件，纯语义检索
            logger.info("No results for '%s', trying hot fallback (no category/exclusion filters)...", message[:40])
            fallback_slots = {
                k: v for k, v in slots.items()
                if k not in ("category", "exclude_brands", "exclude_by_category",
                             "exclude_categories", "exclude_attributes", "exclude_text_terms")
            }
            fallback_query = message
            fallback_state = {**after_intent, "query": fallback_query, "rewritten_query": fallback_query, "slots": fallback_slots}
            after_fallback = await node_retrieve(fallback_state)
            chunks = after_fallback.get("retrieved_chunks", [])
            slots = after_fallback.get("slots", fallback_slots)
            yield {"event": "progress", "data": ProgressEvent(message="未精确匹配，为您推荐热销商品...").model_dump_json()}

        if not chunks:
            # 最终兜底：联网搜索。已有明确品类时，不再清空品类去混推其他商品。
            yield {"event": "progress", "data": ProgressEvent(message="本地商品库未匹配，正在联网搜索...").model_dump_json()}
            after_ws = await node_web_search(after_intent)
            ws_response = after_ws.get("response", "")
            web_results = after_ws.get("_web_results", [])
            yield {"event": "text_delta", "data": TextDeltaEvent(content=ws_response).model_dump_json()}
            for i, wr in enumerate(web_results):
                yield {"event": "web_search_result", "data": WebSearchResultEvent(
                    title=wr.get("title", ""), url=wr.get("url", ""),
                    snippet=wr.get("snippet", ""), index=i + 1, total=len(web_results),
                ).model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── Progress 3: 检索完成，告知命中数量 ──
        yield {"event": "progress", "data": ProgressEvent(message=f"📦 已匹配 {len(chunks)} 件商品，正在为您筛选...").model_dump_json()}

        # ═══════════════════════════════════════════════════════
        # 阶段 2: 商品排序 + Prompt 构建（复用共享辅助函数）
        # ═══════════════════════════════════════════════════════

        from app.services.product_ranker import rank_products

        raw_products = _extract_raw_products(chunks)
        raw_products = _filter_products_by_requested_category(raw_products, slots.get("category", ""))
        raw_products = _filter_products_by_exclusions(raw_products, slots)
        user_prefs = _build_user_prefs(slots)
        intent = after_retrieve.get("intent", "")

        if intent == "scenario_shopping":
            ranked = rank_products(raw_products, user_prefs, intent, top_k=10)
            ranked = _diversify_scenario_products(ranked, max_total=5)
        else:
            ranked = rank_products(raw_products, user_prefs, intent, top_k=3)

        if intent != "scenario_shopping" and len(ranked) < 3 and slots.get("category"):
            logger.info(
                "Only %d ranked products after exclusions; supplementing category=%s",
                len(ranked), slots.get("category")
            )
            chunks = await _retrieve_same_category_supplements(message, slots, chunks)
            raw_products = _extract_raw_products(chunks, limit=30)
            raw_products = _filter_products_by_requested_category(raw_products, slots.get("category", ""))
            raw_products = _filter_products_by_exclusions(raw_products, slots)
            user_prefs = _build_user_prefs(slots)
            ranked = rank_products(raw_products, user_prefs, intent, top_k=3)
        valid_ranked, is_reliable = _validate_ranked_products(ranked)
        logger.info("Ranked: %d products, valid: %d, reliable: %s", len(ranked), len(valid_ranked), is_reliable)

        if not valid_ranked:
            yield {"event": "progress", "data": ProgressEvent(message="未找到匹配商品").model_dump_json()}
            text = "抱歉，暂时没有找到符合您要求的商品。可以试试调整条件重新搜索吗？"
            yield {"event": "text_delta", "data": TextDeltaEvent(content=text).model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── 场景推荐：发送场景元数据事件 ──
        if intent == "scenario_shopping":
            scenario_name = slots.get("scenario", "")
            sub_queries = after_retrieve.get("_scenario_sub_queries", [])
            category_groups = list(dict.fromkeys(
                r.get("category", "") for r in valid_ranked if r.get("category")
            ))
            from app.schemas.sse_events import ScenarioEvent
            yield {
                "event": "scenario",
                "data": ScenarioEvent(
                    scenario=scenario_name,
                    sub_queries=sub_queries,
                    category_groups=category_groups,
                    total_products=len(valid_ranked),
                ).model_dump_json(),
            }

        yield {"event": "progress", "data": ProgressEvent(message="📊 正在生成推荐...").model_dump_json()}

        cards = _assemble_cards(valid_ranked)
        prompt = _build_generation_prompt(message, slots, valid_ranked, is_reliable, after_retrieve.get("intent", ""), history=conversation_history)

        # ═══════════════════════════════════════════════════════
        # 阶段 4: LLM 生成 + 交错输出 — 摘要 → (商品文本 + 卡片) × N → 结语
        # ═══════════════════════════════════════════════════════

        from app.services.llm_client import chat_completion

        logger.info("Starting LLM call for interleaved output...")
        stream = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
            stream=True,
        )

        t_first_token = None
        response_text = ""
        async for event in _stream_interleaved(stream, cards):
            if event["event"] == "text_delta":
                if t_first_token is None:
                    t_first_token = time.monotonic()
                data = json.loads(event["data"])
                response_text += data.get("content", "")
            yield event

        ttft_ms = int((t_first_token - t_start) * 1000) if t_first_token else 0
        logger.info("LLM done: %d chars, TTFT=%dms", len(response_text), ttft_ms)

        # ═══════════════════════════════════════════════════════
        # 阶段 6: 缓存 + 状态回写
        # ═══════════════════════════════════════════════════════

        await cache.set(message, response_text, cards, cache_key=cache_key)

        await _persist_dialog_context(
            conversation_id,
            after_retrieve,
            product_cards=cards,
            intent=after_retrieve.get("intent", ""),
        )

        total_ms = int((time.monotonic() - t_start) * 1000)
        # 仅暴露前端需要的状态字段，不泄露内部标记
        client_slots = {k: v for k, v in slots.items()
                        if not k.startswith("_") and k not in ("missing_slots", "exclude_text_terms")}
        yield {"event": "done", "data": DoneEvent(latency_ms=total_ms, total_cards=len(cards), slots=client_slots).model_dump_json()}

    except Exception as exc:
        logger.exception("Agent pipeline error")
        error = ErrorEvent(message="AI 引擎处理异常，请稍后重试", code="AGENT_ERROR")
        yield {"event": "error", "data": error.model_dump_json()}
        yield {"event": "done", "data": DoneEvent().model_dump_json()}
