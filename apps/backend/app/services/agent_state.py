"""Agent state type definitions - extracted from agent.py."""
from typing import TypedDict


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


_SLOT_KEYS = {
    "category", "price_min", "price_max", "brand_preference", "attributes",
    "scenario", "exclude_brands", "exclude_categories", "exclude_attributes",
    "exclude_text_terms", "exclude_by_category", "missing_slots",
}
