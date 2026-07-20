"""LLM Provider 策略层

将原本散落在 llm_client.py 中的 provider 专属逻辑
(URL 字符串匹配、thinking 开关、模型名覆写)收敛为
统一的 LLMProvider 协议 + 具体实现。
"""
from typing import Protocol

from app.core.config import settings


class LLMProvider(Protocol):
    """LLM Provider strategy interface"""

    base_url: str
    api_key: str
    model: str

    def needs_thinking_disabled(self) -> bool: ...

    def resolve_model(self, requested_model: str | None) -> str: ...

    def get_extra_kwargs(self) -> dict: ...


class DoubaoProvider:
    """火山方舟豆包 Provider"""

    base_url = settings.DOUBAO_BASE_URL
    api_key = settings.DOUBAO_API_KEY
    model = settings.LLM_MODEL

    def needs_thinking_disabled(self) -> bool:
        return True  # Doubao always needs thinking disabled

    def resolve_model(self, requested_model: str | None) -> str:
        return requested_model or self.model

    def get_extra_kwargs(self) -> dict:
        return {"extra_body": {"thinking": {"type": "disabled"}}}


class DeepSeekProvider:
    """DeepSeek Provider"""

    base_url = settings.DEEPSEEK_BASE_URL
    api_key = settings.DEEPSEEK_API_KEY
    model = settings.DEEPSEEK_MODEL or "deepseek-chat"

    def needs_thinking_disabled(self) -> bool:
        return True

    def resolve_model(self, requested_model: str | None) -> str:
        if requested_model and requested_model.startswith("ep-"):
            return self.model  # Override ep- model IDs with deepseek-chat
        return requested_model or self.model

    def get_extra_kwargs(self) -> dict:
        return {"extra_body": {"thinking": {"type": "disabled"}}}


class MimoProvider:
    """Mimo Provider (via DEEPSEEK_API_KEY slot)"""

    base_url = settings.DEEPSEEK_BASE_URL
    api_key = settings.DEEPSEEK_API_KEY
    model = settings.LLM_MODEL

    def needs_thinking_disabled(self) -> bool:
        return True

    def resolve_model(self, requested_model: str | None) -> str:
        return requested_model or self.model

    def get_extra_kwargs(self) -> dict:
        return {"extra_body": {"thinking": {"type": "disabled"}}}


def detect_provider() -> LLMProvider:
    """Auto-detect the active provider from config.

    Priority: DOUBAO_API_KEY -> DEEPSEEK_API_KEY
    """
    if settings.DOUBAO_API_KEY:
        # Check if base_url is actually Mimo
        if "xiaomimimo.com" in (settings.DEEPSEEK_BASE_URL or ""):
            return MimoProvider()
        return DoubaoProvider()
    if settings.DEEPSEEK_API_KEY:
        # Mimo runs through the DEEPSEEK slot with a xiaomimimo.com base_url
        if "xiaomimimo.com" in (settings.DEEPSEEK_BASE_URL or ""):
            return MimoProvider()
        return DeepSeekProvider()
    # Fallback: empty provider
    return DeepSeekProvider()
