"""
Agent 编排 - LangGraph StateGraph 工作流 (facade)
流程: classify_intent -> (missing_slots? -> clarify -> generate | retrieve -> generate) -> SSE stream

This module is now a facade that re-exports from focused submodules:
- agent_state: AgentState, _SLOT_KEYS
- slot_management: category/slot/filter/exclusion helpers
- cart_nlp: cart NLP parsing functions
- scenario: scenario-to-category mapping
- product_assembly: product validation/assembly
- prompts: LLM prompt construction
- agent_nodes: LangGraph node functions
- agent_streaming: SSE streaming helpers

node_cart stays here for monkeypatch compatibility (tests patch agent._find_product_for_cart).
"""
import logging
import time
import re
from typing import AsyncGenerator
from langgraph.graph import StateGraph, END
from app.schemas.sse_events import (
    TextDeltaEvent,
    ProductCardEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    WebSearchResultEvent,
)
from app.core.config import settings
from app.services import cache
from app.services import state_manager as sm
from app.services import cart_service

# ── Re-exports from extracted modules ──

from app.services.agent_state import AgentState, _SLOT_KEYS

from app.services.slot_management import (
    _DIGITAL_CATEGORIES,
    _CATEGORY_PREF_KEYS,
    _FOOD_ONLY_TERMS,
    _FOOD_CATEGORY_TERMS,
    _DIGITAL_QUERY_TERMS,
    _EXPLICIT_CATEGORY_HINTS,
    _BRAND_ALIASES,
    _apply_query_category_hint,
    _apply_history_category_hint,
    _infer_explicit_category_from_text,
    _infer_category_from_query,
    _strip_cross_category_noise,
    _sanitize_slots_for_category,
    _categories_equivalent,
    _has_category_change,
    _prune_previous_slots_for_category_change,
    _current_category_from_context,
    _update_category_context,
    _previous_slots_from_state,
    _build_rewrite_base,
    _product_key_from_chunk,
    _merge_product_chunks,
    _category_matches_request,
    _needs_strict_category_guard,
    _filter_chunks_by_requested_category,
    _filter_products_by_requested_category,
    _filter_chunks_by_exclusions,
    _filter_products_by_exclusions,
    _retrieve_same_category_supplements,
    _expand_brand_aliases,
    _scoped_exclude_brands,
    _normalize_exclusions,
    _build_exclusion_hint,
)

from app.services.cart_nlp import (
    _extract_cart_action,
    _parse_quantity,
    _parse_quantity_delta,
    _quantity_token_to_int,
    _resolve_remaining_product_card,
    _product_from_card,
    _get_cart_backref_cards,
    _find_products_for_multi_cart,
    _cart_item_matches_query,
    _extract_cart_item_index,
    _extract_cart_item_indices,
    _find_product_for_cart,
    _remove_from_cart,
    _update_cart_quantity,
)

from app.services.scenario import (
    _AVAILABLE_CATEGORIES,
    _SCENARIO_FALLBACK_MAP,
    _get_available_categories,
    _map_scenario_to_categories,
    _fuzzy_match_categories,
    _pre_diversify_by_category,
)

from app.services.product_assembly import (
    MIN_MATCH_SCORE,
    _validate_ranked_products,
    _diversify_scenario_products,
    _extract_raw_products,
    _build_user_prefs,
    _assemble_cards,
    _shorten_product_name,
)

from app.services.prompts import _build_generation_prompt

from app.services.agent_nodes.classify import node_classify_intent, _expand_short_query
from app.services.agent_nodes.clarify import node_clarify
from app.services.agent_nodes.retrieve import node_retrieve
from app.services.agent_nodes.generate import node_generate
from app.services.agent_nodes.compare import node_compare, _resolve_compare_targets, _detect_compare_brands
from app.services.agent_nodes.web_search import node_web_search

from app.services.agent_streaming import (
    _safe_emit_boundary,
    _stream_interleaved,
    _find_card_boundaries,
    _nth_occurrence,
    _emit_interleaved,
    _build_cache_key,
    _clean_stream_text,
)

logger = logging.getLogger("agent")


# ── Router ──

def route_after_intent(state: AgentState) -> str:
    """意图路由：闲聊 -> generate, 联网搜索 -> web_search, 对比 -> compare, 缺失信息 -> clarify, 购物车 -> cart, 其他 -> retrieve"""
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
        if AsyncSessionLocal is None:
            state["response"] = "数据库未连接，购物车功能暂不可用。"
            state["product_cards"] = []
            return state
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
                    item_lines = [f"{i+1}. {it.title} ×{it.quantity} - ¥{it.price * it.quantity:.0f}"
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
    内部评测入口 - 运行完整 Agent 图并返回最终状态。
    供 evaluator.py 等内部模块调用，不走 HTTP/SSE。
    """
    initial_state: AgentState = {
        "query": query,
        "session_id": session_id,
        "slots": {},
    }
    final_state = await agent_graph.ainvoke(initial_state, config={"recursion_limit": 10})
    return final_state


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


async def generate_response(
    message: str,
    conversation_id: str | None = None,
    state: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Agent 真流式响应入口 - 被 api/chat.py 调用。

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
        # Demo 模式快速路径 - 跳过 LLM，仅 PostgreSQL 检索 + 模板化回复
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

        # 获取多轮对话历史。缓存 key 也必须包含上下文，避免"便宜一点"等短句误命中。
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
            logger.info("Overriding web_search -> anti_selection: negation detected in multi-turn context")
            after_intent["intent"] = "anti_selection"

        # ── Commerce sanity check: LLM 可能把纯价格/品牌/品类限定词误判为 web_search ──
        #     如 "3000元以下的手表"、"华为手机"、"降噪耳机" - 这些不含"推荐"但明显是导购意图
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
                logger.info("Overriding web_search -> commodity_recommend: commerce keywords detected")
                after_intent["intent"] = "commodity_recommend"
                after_intent["confidence"] = 0.55  # moderate confidence - was overridden

        # ── 联网搜索：外部信息查询 -> web_search node -> 返回结果 ──
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

        # ── 购物车操作：走 cart node -> 直接返回，不做 RAG ──
        if after_intent.get("intent") == "cart_operation":
            yield {"event": "progress", "data": ProgressEvent(message="正在处理您的购物车...").model_dump_json()}
            after_cart = await node_cart(after_intent)
            cart_response = after_cart.get("response", "购物车操作完成。")
            yield {"event": "text_delta", "data": TextDeltaEvent(content=cart_response).model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}
            return

        # ── 商品对比：走 retrieve -> compare -> 返回结构化对比结果 ──
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
            final_state = await agent_graph.ainvoke(after_intent, config={"recursion_limit": 10})
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

        # ── Input safety check: after intent classification, before retrieval ──
        from app.services.agent_nodes.safety_check import node_safety_check_input
        after_intent = await node_safety_check_input(after_intent)
        if after_intent.get("_safety_blocked"):
            yield {"event": "progress", "data": ProgressEvent(message="安全检查未通过").model_dump_json()}
            yield {"event": "text_delta", "data": TextDeltaEvent(content=after_intent["response"]).model_dump_json()}
            yield {"event": "done", "data": DoneEvent(total_cards=0).model_dump_json()}
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
        # 阶段 4: LLM 生成 + 交错输出 - 摘要 -> (商品文本 + 卡片) × N -> 结语
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
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                if t_first_token is None:
                    t_first_token = time.monotonic()
                response_text += chunk.choices[0].delta.content

        ttft_ms = int((t_first_token - t_start) * 1000) if t_first_token else 0
        logger.info("LLM done: %d chars, TTFT=%dms", len(response_text), ttft_ms)

        async for event in _emit_interleaved(response_text, cards):
            yield event

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
