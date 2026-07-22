"""LLM 客户端 - 向后兼容 facade
实际实现在 app/services/llm/ 包中。
"""
from app.services.llm.service import (
    chat_completion, fast_chat_completion,
    get_client, get_fast_client,
    _retry_with_backoff, _is_retryable,
)
from app.services.llm.factory import create_llm_client
from app.services.llm.providers import detect_provider, LLMProvider

# Backward compatible exports
__all__ = [
    "chat_completion", "fast_chat_completion",
    "get_client", "get_fast_client", "create_llm_client",
    "detect_provider", "LLMProvider",
    "_retry_with_backoff", "_is_retryable",
]
