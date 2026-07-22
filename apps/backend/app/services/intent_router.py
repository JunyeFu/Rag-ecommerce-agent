"""
意图修正路由器 - 从 generate_response 提取的意图覆盖逻辑

顺序（pipeline 中按此调用，中间有 early return）:
1. apply_cart_keyword_override  -> 然后 pipeline 检查 chitchat early return
2. apply_negation_override       -> 然后 apply_commerce_sanity_override -> 然后 pipeline 检查 web_search early return
3. apply_cart_confirm_context   -> 然后 pipeline 检查 cart_operation early return
"""
import re
import logging

logger = logging.getLogger("intent_router")

_CART_KEYWORDS = [
    "购物车", "加购", "加入购物车", "加到购物车", "添加到购物车",
    "删除", "移除", "清空", "数量改", "改成", "改为",
    "设为", "设置为", "调整为", "调到", "改到", "加一件", "减一件",
    "下单", "结算", "结账", "确认下单",
]

_NEG_KEYWORDS = ["不要", "除了", "非", "不含", "排除", "拒绝", "去掉", "避开", "别"]

_COMMERCE_KEYWORDS = [
    r"\d+元", r"\d+块", r"以下", r"以内", r"以上", r"左右",
    "买", "购", "想搞", "整一个",
    "手机", "耳机", "手表", "电脑", "平板", "相机", "音箱", "键盘", "鼠标",
    "洗面奶", "面霜", "防晒", "精华", "面膜", "口红", "粉底", "化妆",
    "跑鞋", "运动鞋", "篮球鞋", "羽绒服", "T恤", "卫衣", "背包", "行李箱",
    "降噪", "蓝牙", "无线", "有线", "充电", "续航", "防水", "防摔",
    "推荐", "哪个好", "怎么选", "什么牌子", "性价比",
]

_WEB_ONLY_KEYWORDS = [
    "最新", "新闻", "趋势", "流行", "网上", "搜索", "查一下", "最近有什么",
    "现在什么", "什么时候", "2025", "2026", "今年", "双11", "618", "双十一",
]

_CART_CONFIRM_KEYWORDS = {"确认下单", "确认", "是的", "确定", "没错", "下单", "结算"}


def apply_cart_keyword_override(state: dict, message: str) -> dict:
    """购物车关键词检测 -> 强制 cart_operation"""
    if any(kw in message for kw in _CART_KEYWORDS):
        logger.info("Intent override: cart keyword detected, forcing cart_operation")
        state["intent"] = "cart_operation"
    return state


def apply_negation_override(state: dict, message: str, history: list[dict]) -> dict:
    """否定语义检测 -> web_search 改 anti_selection"""
    has_negation_in_query = any(kw in message for kw in _NEG_KEYWORDS)
    has_negation_slots = bool(
        state.get("slots", {}).get("exclude_brands")
        or state.get("slots", {}).get("exclude_categories")
        or state.get("slots", {}).get("exclude_text_terms")
    )
    has_history = len(history) >= 2
    if state.get("intent") == "web_search" and (has_negation_in_query or has_negation_slots) and has_history:
        logger.info("Overriding web_search -> anti_selection: negation detected in multi-turn context")
        state["intent"] = "anti_selection"
    return state


def apply_commerce_sanity_override(state: dict, message: str) -> dict:
    """电商关键词检测 -> web_search 改 commodity_recommend"""
    if state.get("intent") != "web_search":
        return state
    has_commerce = any(
        (re.search(kw, message) if kw.startswith(r"\d") else kw in message)
        for kw in _COMMERCE_KEYWORDS
    )
    has_web_only = any(kw in message for kw in _WEB_ONLY_KEYWORDS)
    if has_commerce and not has_web_only:
        logger.info("Overriding web_search -> commodity_recommend: commerce keywords detected")
        state["intent"] = "commodity_recommend"
        state["confidence"] = 0.55
    return state


def apply_cart_confirm_context_override(state: dict, message: str, history: list[dict]) -> dict:
    """购物车确认上下文检测 -> 上轮是订单确认页，本轮回复视为确认"""
    if state.get("intent") == "cart_operation":
        return state
    if not history:
        return state
    last_assistant = ""
    for m in reversed(history):
        if m.get("role") == "assistant":
            last_assistant = m.get("content", "")
            break
    if ("订单确认" in last_assistant or "确认下单" in last_assistant) and \
       any(kw in message for kw in _CART_CONFIRM_KEYWORDS):
        logger.info("Cart context override: detected checkout confirmation reply")
        state["intent"] = "cart_operation"
        state["slots"] = state.get("slots", {})
    return state
