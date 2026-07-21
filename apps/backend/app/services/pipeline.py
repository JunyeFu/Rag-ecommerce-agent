"""
Agent 流水线 - 从 generate_response 提取的意图分发架构

generate_response 退化为 ~40 行调度器，每个分支由独立的 Handler 异步生成器处理。
Handler 接口: async def handle(ctx: PipelineContext) -> AsyncGenerator[dict, None]
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

from app.core.config import settings
from app.services import cache
from app.services import state_manager as sm
from app.services.agent_state import AgentState
from app.services.intent_router import (
    apply_cart_keyword_override,
    apply_negation_override,
    apply_commerce_sanity_override,
    apply_cart_confirm_context_override,
)
from app.services.agent_nodes.classify import node_classify_intent
from app.services.agent_nodes.web_search import node_web_search
from app.services.agent_nodes.compare import node_compare, _resolve_compare_targets
from app.services.agent_nodes.retrieve import node_retrieve
from app.services.agent_nodes.safety_check import node_safety_check_input
from app.services.product_ranker import rank_products
from app.services.product_assembly import (
    _extract_raw_products,
    _build_user_prefs,
    _validate_ranked_products,
    _diversify_scenario_products,
    _assemble_cards,
)
from app.services.slot_management import (
    _filter_products_by_requested_category,
    _filter_products_by_exclusions,
    _retrieve_same_category_supplements,
)
from app.services.prompts import _build_generation_prompt
from app.services.agent_streaming import _build_cache_key, _emit_interleaved
from app.services.llm_client import chat_completion
from app.schemas.sse_events import (
    TextDeltaEvent,
    ProductCardEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    WebSearchResultEvent,
)

logger = logging.getLogger("pipeline")


@dataclass
class PipelineContext:
    """流水线上下文 - 在 pipeline 与 handler 之间传递"""
    message: str
    conversation_id: str | None
    state: dict | None
    t_start: float
    history: list[dict] = field(default_factory=list)
    after_intent: dict = field(default_factory=dict)
    cache_key: str = ""


# ═══════════════════════════════════════════════════════
# Handlers - 每个 handler 是独立的异步生成器
# ═══════════════════════════════════════════════════════

async def handle_demo(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """Demo 模式 - 跳过 LLM，仅 PostgreSQL 检索 + 模板化回复"""
    from app.services import rag as _rag_module

    logger.info("DEMO_MODE: mock SSE for query=%s", ctx.message[:60])
    yield {"event": "progress", "data": ProgressEvent(message="[演示模式] 正在检索商品...").model_dump_json()}
    result = await _rag_module.retrieve(query=ctx.message, top_k=settings.RETRIEVAL_TOP_K)
    chunks = result.get("chunks", [])
    if chunks:
        yield {"event": "text_delta", "data": TextDeltaEvent(
            content=f"[演示模式] 为您找到 {len(chunks[:5])} 款相关商品：\n\n"
        ).model_dump_json()}
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
        yield {"event": "text_delta", "data": TextDeltaEvent(
            content="[演示模式] 未找到匹配商品，请尝试其他关键词。\n"
        ).model_dump_json()}
    yield {"event": "done", "data": DoneEvent(
        latency_ms=0, total_cards=min(len(chunks), 5), message="demo-mode"
    ).model_dump_json()}


async def handle_cache_hit(ctx: PipelineContext, cached: dict) -> AsyncGenerator[dict, None]:
    """缓存命中 - 直接输出缓存的响应和卡片"""
    response_text = cached["response"]
    cards = cached["cards"]
    if len(cards) > 3:
        cards = cards[:3]
    async for evt in _emit_interleaved(response_text, cards):
        yield evt
    elapsed = int((time.monotonic() - ctx.t_start) * 1000)
    yield {"event": "done", "data": DoneEvent(latency_ms=elapsed, message="cache-hit").model_dump_json()}


async def handle_chitchat(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """闲聊 - 返回引导性回复"""
    yield {"event": "progress", "data": ProgressEvent(message="已理解您的问题，正在回复...").model_dump_json()}
    text = ("你可以告诉我具体的需求，比如「推荐一款降噪耳机」"
            "「300元以内的运动鞋」「送女朋友的生日礼物」，我会帮你找到合适的商品～")
    yield {"event": "text_delta", "data": TextDeltaEvent(content=text).model_dump_json()}
    yield {"event": "done", "data": DoneEvent().model_dump_json()}


async def handle_web_search(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """联网搜索 - 调用 web_search node 并返回结果"""
    yield {"event": "progress", "data": ProgressEvent(message="正在联网搜索...").model_dump_json()}
    after_ws = await node_web_search(ctx.after_intent)
    ws_response = after_ws.get("response", "")
    web_results = after_ws.get("_web_results", [])

    yield {"event": "text_delta", "data": TextDeltaEvent(content=ws_response).model_dump_json()}
    for i, wr in enumerate(web_results):
        yield {"event": "web_search_result", "data": WebSearchResultEvent(
            title=wr.get("title", ""),
            url=wr.get("url", ""),
            snippet=wr.get("snippet", ""),
            index=i + 1,
            total=len(web_results),
        ).model_dump_json()}
    yield {"event": "done", "data": DoneEvent().model_dump_json()}


async def handle_cart(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """购物车操作 - 调用 node_cart 并返回响应"""
    from app.services.agent import node_cart

    yield {"event": "progress", "data": ProgressEvent(message="正在处理您的购物车...").model_dump_json()}
    after_cart = await node_cart(ctx.after_intent)
    cart_response = after_cart.get("response", "购物车操作完成。")
    yield {"event": "text_delta", "data": TextDeltaEvent(content=cart_response).model_dump_json()}
    yield {"event": "done", "data": DoneEvent().model_dump_json()}


async def handle_compare(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """商品对比 - 检索 + 对比 + 返回结构化结果"""
    from app.schemas.sse_events import CompareEvent

    yield {"event": "progress", "data": ProgressEvent(message="正在检索商品，准备对比...").model_dump_json()}

    target_ids = await _resolve_compare_targets(
        query=ctx.message,
        conversation_id=ctx.conversation_id or "",
        history=ctx.history,
    )

    if target_ids and len(target_ids) >= 2:
        logger.info("Compare: using resolved target product_ids: %s", target_ids)
        ctx.after_intent["_target_product_ids"] = target_ids
        after_compare = await node_compare(ctx.after_intent)
    else:
        after_retrieve = await node_retrieve(ctx.after_intent)
        after_compare = await node_compare(after_retrieve)

    compare_response = after_compare.get("response", "")
    compare_cards = after_compare.get("product_cards", [])
    compare_dims = after_compare.get("_comparison_dims", [])

    if compare_response:
        yield {"event": "text_delta", "data": TextDeltaEvent(content=compare_response).model_dump_json()}

    if compare_dims:
        yield {"event": "compare", "data": CompareEvent(dimensions=compare_dims).model_dump_json()}

    for i, card in enumerate(compare_cards):
        yield {"event": "product_cards", "data": ProductCardEvent(
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
        ).model_dump_json()}

    total_ms = int((time.monotonic() - ctx.t_start) * 1000)
    yield {"event": "done", "data": DoneEvent(
        total_cards=len(compare_cards), latency_ms=total_ms
    ).model_dump_json()}


async def handle_clarify(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """澄清反问 - 调用 agent_graph 获取追问并返回"""
    from app.schemas.sse_events import ClarifyEvent
    from app.services.agent import route_after_intent, agent_graph, _persist_dialog_context

    await _persist_dialog_context(ctx.conversation_id, ctx.after_intent)
    yield {"event": "progress", "data": ProgressEvent(message="正在分析您的需求细节...").model_dump_json()}
    final_state = await agent_graph.ainvoke(ctx.after_intent, config={"recursion_limit": 10})
    clarify_text = final_state.get("response", "")
    missing_list = ctx.after_intent.get("slots", {}).get("missing_slots", [])
    if not isinstance(missing_list, list):
        missing_list = []
    yield {
        "event": "clarify",
        "data": ClarifyEvent(
            question=clarify_text or "能再具体说说您的需求吗？",
            missing_slots=missing_list,
        ).model_dump_json(),
    }
    yield {"event": "done", "data": DoneEvent().model_dump_json()}


async def handle_safety_block(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """安全检查未通过 - 返回安全提示"""
    yield {"event": "progress", "data": ProgressEvent(message="安全检查未通过").model_dump_json()}
    yield {"event": "text_delta", "data": TextDeltaEvent(
        content=ctx.after_intent["response"]
    ).model_dump_json()}
    yield {"event": "done", "data": DoneEvent(total_cards=0).model_dump_json()}


async def handle_retrieve(ctx: PipelineContext) -> AsyncGenerator[dict, None]:
    """主检索路径 - retrieve -> fallback -> rank -> LLM stream -> cache + persist"""
    from app.schemas.sse_events import ScenarioEvent
    from app.services.agent import _persist_dialog_context

    yield {"event": "progress", "data": ProgressEvent(message="已理解需求，正在检索商品...").model_dump_json()}

    after_retrieve = await node_retrieve(ctx.after_intent)
    chunks = after_retrieve.get("retrieved_chunks", [])
    slots = after_retrieve.get("slots", {})

    # 检索 fallback 策略
    if not chunks:
        if slots.get("category"):
            logger.info("No precise results for '%s', expanding within category=%s",
                        ctx.message[:40], slots.get("category"))
            chunks = await _retrieve_same_category_supplements(ctx.message, slots, chunks)

    if not chunks and not slots.get("category"):
        logger.info("No results for '%s', trying hot fallback...", ctx.message[:40])
        fallback_slots = {
            k: v for k, v in slots.items()
            if k not in ("category", "exclude_brands", "exclude_by_category",
                         "exclude_categories", "exclude_attributes", "exclude_text_terms")
        }
        fallback_state = {**ctx.after_intent, "query": ctx.message,
                           "rewritten_query": ctx.message, "slots": fallback_slots}
        after_fallback = await node_retrieve(fallback_state)
        chunks = after_fallback.get("retrieved_chunks", [])
        slots = after_fallback.get("slots", fallback_slots)
        yield {"event": "progress", "data": ProgressEvent(
            message="未精确匹配，为您推荐热销商品..."
        ).model_dump_json()}

    if not chunks:
        # 最终兜底：联网搜索
        yield {"event": "progress", "data": ProgressEvent(
            message="本地商品库未匹配，正在联网搜索..."
        ).model_dump_json()}
        after_ws = await node_web_search(ctx.after_intent)
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

    yield {"event": "progress", "data": ProgressEvent(
        message=f"📦 已匹配 {len(chunks)} 件商品，正在为您筛选..."
    ).model_dump_json()}

    # 商品排序
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
        logger.info("Only %d ranked products; supplementing category=%s",
                    len(ranked), slots.get("category"))
        chunks = await _retrieve_same_category_supplements(ctx.message, slots, chunks)
        raw_products = _extract_raw_products(chunks, limit=30)
        raw_products = _filter_products_by_requested_category(raw_products, slots.get("category", ""))
        raw_products = _filter_products_by_exclusions(raw_products, slots)
        user_prefs = _build_user_prefs(slots)
        ranked = rank_products(raw_products, user_prefs, intent, top_k=3)

    valid_ranked, is_reliable = _validate_ranked_products(ranked)
    logger.info("Ranked: %d products, valid: %d, reliable: %s",
                len(ranked), len(valid_ranked), is_reliable)

    if not valid_ranked:
        yield {"event": "progress", "data": ProgressEvent(message="未找到匹配商品").model_dump_json()}
        yield {"event": "text_delta", "data": TextDeltaEvent(
            content="抱歉，暂时没有找到符合您要求的商品。可以试试调整条件重新搜索吗？"
        ).model_dump_json()}
        yield {"event": "done", "data": DoneEvent().model_dump_json()}
        return

    # 场景推荐：发送场景元数据事件
    if intent == "scenario_shopping":
        scenario_name = slots.get("scenario", "")
        sub_queries = after_retrieve.get("_scenario_sub_queries", [])
        category_groups = list(dict.fromkeys(
            r.get("category", "") for r in valid_ranked if r.get("category")
        ))
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
    prompt = _build_generation_prompt(
        ctx.message, slots, valid_ranked, is_reliable,
        after_retrieve.get("intent", ""), history=ctx.history,
    )

    # LLM 流式生成
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

    ttft_ms = int((t_first_token - ctx.t_start) * 1000) if t_first_token else 0
    logger.info("LLM done: %d chars, TTFT=%dms", len(response_text), ttft_ms)

    async for event in _emit_interleaved(response_text, cards):
        yield event

    # 缓存 + 状态回写
    await cache.set(ctx.message, response_text, cards, cache_key=ctx.cache_key)
    await _persist_dialog_context(
        ctx.conversation_id,
        after_retrieve,
        product_cards=cards,
        intent=after_retrieve.get("intent", ""),
    )

    total_ms = int((time.monotonic() - ctx.t_start) * 1000)
    client_slots = {k: v for k, v in slots.items()
                    if not k.startswith("_") and k not in ("missing_slots", "exclude_text_terms")}
    yield {"event": "done", "data": DoneEvent(
        latency_ms=total_ms, total_cards=len(cards), slots=client_slots
    ).model_dump_json()}


# ═══════════════════════════════════════════════════════
# Pipeline 调度器 - 替代原 443 行 generate_response
# ═══════════════════════════════════════════════════════

async def generate_response(
    message: str,
    conversation_id: str | None = None,
    state: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """Agent 流式响应入口 - 意图分发 Pipeline"""
    from app.services.agent import route_after_intent, _persist_dialog_context

    ctx = PipelineContext(
        message=message,
        conversation_id=conversation_id,
        state=state,
        t_start=time.monotonic(),
    )

    try:
        # Demo 模式
        if settings.DEMO_MODE:
            async for evt in handle_demo(ctx):
                yield evt
            return

        yield {"event": "progress", "data": ProgressEvent(message="正在分析您的需求...").model_dump_json()}
        yield {"event": "text_delta", "data": TextDeltaEvent(content="收到，我马上帮你处理。\n\n").model_dump_json()}

        # 获取多轮对话历史 + 缓存 key
        ctx.history = await sm.get_recent_messages(conversation_id or "", limit=6)
        ctx.cache_key = _build_cache_key(message, conversation_id, ctx.history)

        # 缓存检查
        cached = await cache.get(message, cache_key=ctx.cache_key)
        if cached:
            async for evt in handle_cache_hit(ctx, cached):
                yield evt
            return

        # 意图分类
        initial_state: AgentState = {
            "query": message,
            "session_id": conversation_id or "",
            "cart_session_id": (state or {}).get("cart_session_id", "") if isinstance(state, dict) else "",
            "user_id": (state or {}).get("user_id", "") if isinstance(state, dict) else "",
            "slots": (state or {}).get("slots", {}) if isinstance(state, dict) else {},
            "category_context": (state or {}).get("category_context", {}) if isinstance(state, dict) else {},
            "product_cards": (state or {}).get("product_cards", []) if isinstance(state, dict) else [],
            "history": ctx.history,
        }
        ctx.after_intent = await node_classify_intent(initial_state)
        if ctx.after_intent.get("intent") != "chitchat":
            await _persist_dialog_context(conversation_id, ctx.after_intent)

        # 意图修正：购物车关键词
        apply_cart_keyword_override(ctx.after_intent, message)

        # 闲聊
        if ctx.after_intent.get("intent") == "chitchat":
            async for evt in handle_chitchat(ctx):
                yield evt
            return

        # 意图修正：否定语义 + 电商关键词
        apply_negation_override(ctx.after_intent, message, ctx.history)
        apply_commerce_sanity_override(ctx.after_intent, message)

        # 联网搜索
        if ctx.after_intent.get("intent") == "web_search":
            async for evt in handle_web_search(ctx):
                yield evt
            return

        # 意图修正：购物车确认上下文
        apply_cart_confirm_context_override(ctx.after_intent, message, ctx.history)

        # 购物车操作
        if ctx.after_intent.get("intent") == "cart_operation":
            async for evt in handle_cart(ctx):
                yield evt
            return

        # 商品对比
        if ctx.after_intent.get("intent") == "commodity_compare":
            async for evt in handle_compare(ctx):
                yield evt
            return

        # 澄清反问
        route = route_after_intent(ctx.after_intent)
        if route == "clarify":
            async for evt in handle_clarify(ctx):
                yield evt
            return

        # 输入安全检查
        ctx.after_intent = await node_safety_check_input(ctx.after_intent)
        if ctx.after_intent.get("_safety_blocked"):
            async for evt in handle_safety_block(ctx):
                yield evt
            return

        # 主检索路径
        async for evt in handle_retrieve(ctx):
            yield evt

    except Exception as exc:
        logger.exception("Agent pipeline error")
        yield {"event": "error", "data": ErrorEvent(
            message="AI 引擎处理异常，请稍后重试", code="AGENT_ERROR"
        ).model_dump_json()}
        yield {"event": "done", "data": DoneEvent().model_dump_json()}
