"""LLM 客户端 - Strategy + Factory 模块化实现

公共 API:
    chat_completion, fast_chat_completion,
    get_client, get_fast_client, create_llm_client
"""
from app.services.llm.service import (
    chat_completion,
    fast_chat_completion,
    get_client,
    get_fast_client,
)
from app.services.llm.factory import create_llm_client
from app.services.llm.providers import detect_provider, LLMProvider

__all__ = [
    "chat_completion",
    "fast_chat_completion",
    "get_client",
    "get_fast_client",
    "create_llm_client",
    "detect_provider",
    "LLMProvider",
]
