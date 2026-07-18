"""Safety check node for LangGraph pipeline."""
import logging

from app.services.agent_state import AgentState
from app.services.safety_service import check_input_safety, check_output_safety

logger = logging.getLogger("agent")


async def node_safety_check_input(state: AgentState) -> AgentState:
    """Check user query safety before processing."""
    query = state.get("query", "")
    is_safe, reason = await check_input_safety(query)
    if not is_safe:
        state["response"] = f"抱歉，您的请求无法处理。{reason}"
        state["product_cards"] = []
        state["_safety_blocked"] = True
    return state


async def node_safety_check_output(state: AgentState) -> AgentState:
    """Check LLM output safety before returning to user."""
    if state.get("_safety_blocked"):
        return state
    response = state.get("response", "")
    if response:
        is_safe, reason = await check_output_safety(response)
        if not is_safe:
            state["response"] = "抱歉，生成的内容包含敏感信息，已过滤。请尝试换一种方式提问。"
            state["product_cards"] = []
    return state
