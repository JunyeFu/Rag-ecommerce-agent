"""
Clarification node - generates follow-up questions when information is missing.

Extracted from agent.py.
"""
import logging

from app.services.agent_state import AgentState

logger = logging.getLogger("agent")


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
    logger.info("Clarify: missing=%s category=%s -> response=%s", missing, category, state["response"])
    return state
