"""LLM 客户端工厂

支持显式参数注入（测试用）或基于 detect_provider() 自动选择。
"""
from openai import AsyncOpenAI

from app.services.llm.providers import LLMProvider, detect_provider


def create_llm_client(
    api_key: str = "",
    base_url: str = "",
    timeout: float = 30.0,
) -> AsyncOpenAI:
    """Factory function - creates AsyncOpenAI client from provider or explicit params"""
    if api_key and base_url:
        return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    provider: LLMProvider = detect_provider()
    return AsyncOpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
        timeout=timeout,
    )
