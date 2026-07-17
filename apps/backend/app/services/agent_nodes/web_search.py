"""
Web search node - DuckDuckGo search with LLM knowledge fallback.

Extracted from agent.py.
"""
import logging

from app.services.agent_state import AgentState
from app.services.web_search import search_web, format_search_results, WEB_SEARCH_PROMPT, WEB_SEARCH_FALLBACK_PROMPT

logger = logging.getLogger("agent")


async def node_web_search(state: AgentState) -> AgentState:
    """联网搜索节点 - DuckDuckGo 搜索 + LLM 知识兜底"""
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
