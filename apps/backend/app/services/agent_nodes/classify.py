"""
Intent classification node - classifies user intent and extracts slots.

Extracted from agent.py.
"""
import logging

from app.services.agent_state import AgentState
from app.services.intent import classify_intent, extract_slots, rewrite_query, extract_negation_slots
from app.services.slot_management import (
    _apply_query_category_hint,
    _apply_history_category_hint,
    _previous_slots_from_state,
    _has_category_change,
    _prune_previous_slots_for_category_change,
    _update_category_context,
    _normalize_exclusions,
    _sanitize_slots_for_category,
    _build_rewrite_base,
)

logger = logging.getLogger("agent")


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
        logger.info("Short query expanded: '%s' -> '%s'", query, expanded)

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
            # 合并而非覆盖 - 保留 merge loop 已累积的历史排除条件
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

    "鞋" -> "运动鞋 休闲鞋 皮鞋 跑步鞋 鞋类推荐"
    "平板" -> "平板电脑 iPad 安卓平板 华为平板 推荐"
    """
    prompt = f"""用户输入了一个非常短的商品搜索词：「{query}」

这个搜索词太短，缺乏语义上下文，会导致商品检索效果很差。请你分析这个词可能指代的商品品类，列出该品类下最常见的 5-8 个子品类或相关热门搜索词，用空格分隔。

例如：
- "鞋" -> "运动鞋 休闲鞋 皮鞋 跑步鞋 篮球鞋 帆布鞋 鞋类推荐"
- "平板" -> "平板电脑 iPad 安卓平板 华为平板 小米平板 学习平板"
- "耳机" -> "蓝牙耳机 降噪耳机 无线耳机 头戴式耳机 入耳式耳机 运动耳机"

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
            logger.info("Short query expanded: '%s' -> '%s'", query, expanded)
            return expanded
    except Exception as e:
        logger.warning("Short query expansion failed for '%s': %s", query, e)

    return query
