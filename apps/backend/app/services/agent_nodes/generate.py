"""
Generation node - produces LLM recommendation responses with product cards.

Extracted from agent.py.
"""
import logging

from app.services.agent_state import AgentState
from app.services.llm_client import chat_completion
from app.services.product_assembly import (
    _extract_raw_products,
    _validate_ranked_products,
    _assemble_cards,
    _build_user_prefs,
)
from app.services.prompts import _build_generation_prompt
from app.services.slot_management import (
    _filter_products_by_requested_category,
    _filter_products_by_exclusions,
)

logger = logging.getLogger("agent")


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
