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



# generate_response 已提取到 pipeline.py（442行 -> 40行调度器）
from app.services.pipeline import generate_response  # noqa: E402
