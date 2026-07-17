"""LLM 调用服务 - 统一的 chat_completion 核心

将原 fast_chat_completion / chat_completion 的重复逻辑（~80%）收敛为
单个 _execute_completion，由 provider 策略提供模型解析与 extra_kwargs。
"""
import asyncio
import time
import logging

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from app.services.llm.providers import LLMProvider, detect_provider
from app.services.llm.factory import create_llm_client

logger = logging.getLogger("llm_client")

# ── 重试配置 ──
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # 指数退避: 1s, 2s, 4s...
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

_provider: LLMProvider | None = None
_client: AsyncOpenAI | None = None
_fast_client: AsyncOpenAI | None = None


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = detect_provider()
    return _provider


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = create_llm_client()
    return _client


def get_fast_client() -> AsyncOpenAI:
    global _fast_client
    if _fast_client is None:
        _fast_client = create_llm_client(timeout=15.0)
    return _fast_client


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUSES
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return False


async def _retry_with_backoff(fn, name: str = "llm") -> str:
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES and _is_retryable(exc):
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("%s attempt %d/%d failed, retrying in %.1fs: %s",
                             name, attempt + 1, MAX_RETRIES + 1, delay, exc)
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


async def _execute_completion(
    client: AsyncOpenAI,
    messages: list[dict],
    model: str | None,
    temperature: float,
    max_tokens: int,
    stream: bool,
    name: str = "llm",
) -> str | AsyncOpenAI:
    """Core completion logic - shared by fast_chat_completion and chat_completion"""
    provider = _get_provider()
    _model = provider.resolve_model(model)
    extra_kwargs = provider.get_extra_kwargs() if provider.needs_thinking_disabled() else {}
    start = time.time()

    if stream:
        response = await client.chat.completions.create(
            model=_model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=True, **extra_kwargs,
        )
        logger.info("LLM stream started: model=%s", _model)
        return response

    async def _call():
        response = await client.chat.completions.create(
            model=_model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=False, **extra_kwargs,
        )
        elapsed = time.time() - start
        # Fix M-6: validate empty choices
        if not response.choices:
            logger.warning("LLM returned empty choices: model=%s, tokens=%s", _model, getattr(response, 'usage', '?'))
            return ""
        content = response.choices[0].message.content or ""
        logger.info("%s: model=%s, tokens=%s, elapsed=%.1fs", name, _model, getattr(response, 'usage', '?'), elapsed)
        return content

    return await _retry_with_backoff(_call, name=name)


async def fast_chat_completion(messages, temperature=0.1, max_tokens=200) -> str:
    start = time.time()
    try:
        return await _execute_completion(
            get_fast_client(), messages, None, temperature, max_tokens, stream=False, name="Fast LLM"
        )
    except Exception as exc:
        logger.error("Fast LLM failed after %.1fs: %s", time.time() - start, exc)
        raise


async def chat_completion(messages, model=None, temperature=0.7, max_tokens=2048, stream=False, client=None) -> str | AsyncOpenAI:
    _c = client or get_client()
    start = time.time()
    try:
        return await _execute_completion(
            _c, messages, model, temperature, max_tokens, stream=stream, name="LLM"
        )
    except Exception as exc:
        logger.error("LLM call failed after %.1fs: %s", time.time() - start, exc)
        raise
