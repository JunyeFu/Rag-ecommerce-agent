"""
LLM 调用封装 — 多 Provider 自适应 (OpenAI-compatible)
遵循开发规约 v2.0 §3.3.3: 大模型调用统一封装

优先级: DOUBAO_API_KEY → DEEPSEEK_API_KEY
当前使用: Mimo v2.5 (via DEEPSEEK slot)
可测试性: create_llm_client() 接受参数注入，测试时可传 mock client。
"""
import asyncio
import time
import logging
from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError
from app.core.config import settings

logger = logging.getLogger("llm_client")

# ── 重试配置 ──
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # 指数退避: 1s, 2s, 4s...
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _needs_thinking_disabled(base_url: str, model: str) -> bool:
    """Doubao 和 Mimo 默认开启 CoT thinking，需要显式禁用以降低 TTFT。"""
    return (
        "volces.com" in base_url          # Doubao
        or "xiaomimimo.com" in base_url   # Mimo
        or model.startswith("ep-")        # Doubao endpoint model
    )


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否可以重试"""
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUSES
    # asyncio.TimeoutError 也重试
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return False


async def _retry_with_backoff(fn, name: str = "llm") -> str:
    """带指数退避的重试执行器，最多重试 MAX_RETRIES 次"""
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


def create_llm_client(
    api_key: str = "",
    base_url: str = "",
    timeout: float = 30.0,
) -> AsyncOpenAI:
    """工厂函数 — 优先 Doubao（比赛主用），回退 DeepSeek"""
    key = api_key or settings.DOUBAO_API_KEY or settings.DEEPSEEK_API_KEY
    url = base_url or settings.DOUBAO_BASE_URL or settings.DEEPSEEK_BASE_URL
    return AsyncOpenAI(
        api_key=key,
        base_url=url,
        timeout=timeout,
    )


# 模块级默认实例 (生产使用)
_client: AsyncOpenAI | None = None
_fast_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """懒加载 LLM 客户端（Doubao，用于最终生成）"""
    global _client
    if _client is None:
        _client = create_llm_client()
    return _client


def get_fast_client() -> AsyncOpenAI:
    """懒加载快速 LLM 客户端（轻量任务：意图/槽位/反问/否定/查询扩展）"""
    global _fast_client
    if _fast_client is None:
        _fast_client = create_llm_client(timeout=15.0)
    return _fast_client


async def fast_chat_completion(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 200,
) -> str:
    """
    轻量任务快速 LLM 调用（~0.5s）。
    用于意图分类、槽位提取、查询改写等简单结构化输出任务。
    支持自动重试：网络错误/超时/429/5xx 最多重试 2 次。
    """
    start = time.time()

    async def _call():
        client = get_fast_client()
        model = settings.LLM_MODEL
        _base = str(client.base_url)
        if "deepseek.com" in _base and model.startswith("ep-"):
            model = settings.DEEPSEEK_MODEL or "deepseek-chat"

        extra_kwargs = {}
        if _needs_thinking_disabled(_base, model):
            extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )
        elapsed = time.time() - start
        content = response.choices[0].message.content or ""
        logger.info("Fast LLM: model=%s, tokens=%s, elapsed=%.1fs",
                    model, getattr(response, 'usage', '?'), elapsed)
        return content

    try:
        return await _retry_with_backoff(_call, name="fast_llm")
    except Exception as exc:
        elapsed = time.time() - start
        logger.error("Fast LLM failed after %.1fs: %s", elapsed, exc)
        raise


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
    client: AsyncOpenAI | None = None,
) -> str | AsyncOpenAI:
    """
    调用 LLM 生成回答

    Args:
        messages: 对话消息列表
        model: 模型名 (默认 settings.LLM_MODEL)
        temperature: 温度参数
        max_tokens: 最大 token 数
        stream: True 返回异步流对象 (SSE), False 返回完整文本
        client: 可注入的 AsyncOpenAI 实例 (测试用)

    Returns:
        stream=False: 完整回答文本
        stream=True: AsyncOpenAI 流对象
    """
    _c = client or get_client()
    _model = model or settings.LLM_MODEL
    # 自动匹配模型名：DeepSeek 用 deepseek-chat，Doubao 用 LLM_MODEL
    if not model:
        _base = str(_c.base_url)
        if "deepseek.com" in _base and _model.startswith("ep-"):
            _model = settings.DEEPSEEK_MODEL or "deepseek-chat"
    start = time.time()

    # Doubao / Mimo 默认开启 CoT thinking，导致 TTFT 暴涨。
    # 必须显式关闭 thinking。
    extra_kwargs = {}
    if _needs_thinking_disabled(str(_c.base_url), _model):
        extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    try:
        if stream:
            # 流式调用不重试（已开始发送数据）
            response = await _c.chat.completions.create(
                model=_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **extra_kwargs,
            )
            logger.info("LLM stream started: model=%s", _model)
            return response
        else:
            async def _call():
                response = await _c.chat.completions.create(
                    model=_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    **extra_kwargs,
                )
                elapsed = time.time() - start
                content = response.choices[0].message.content or ""
                logger.info("LLM call: model=%s, tokens=%s, elapsed=%.1fs",
                            _model, getattr(response, 'usage', '?'), elapsed)
                return content
            return await _retry_with_backoff(_call, name="llm")
    except Exception as exc:
        elapsed = time.time() - start
        logger.error("LLM call failed after %.1fs: %s", elapsed, exc)
        raise
