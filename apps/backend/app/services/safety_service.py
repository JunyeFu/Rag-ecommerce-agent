"""Content safety filter using LLM provider's moderation capabilities."""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("safety")

_UNSAFE_INPUT_KEYWORDS = ["色情", "暴力", "赌博", "毒品", "枪支", "炸弹", "自杀", "自残"]
_UNSAFE_OUTPUT_KEYWORDS = ["色情", "暴力描写", "犯罪指导", "有害物质制作"]


async def _doubao_moderation(text: str) -> tuple[bool, str] | None:
    """
    Call Doubao moderation API. Returns None if not configured or on failure.
    POST to {base_url}/moderation with {"input": text}
    """
    api_key = settings.DOUBAO_API_KEY
    base_url = (settings.DOUBAO_BASE_URL or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{base_url}/moderation",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": text},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data", {}).get("flagged", False):
                    categories = data.get("data", {}).get("categories", [])
                    return False, f"内容触发安全策略: {','.join(categories)}"
                return True, ""
    except Exception as e:
        logger.warning("Moderation API failed, using fallback: %s", e)
    return None


async def check_input_safety(text: str) -> tuple[bool, str]:
    """
    Check user input for safety. Returns (is_safe, reason).
    Uses Doubao moderation API if configured, otherwise uses keyword-based fallback.
    """
    result = await _doubao_moderation(text)
    if result is not None:
        return result
    for kw in _UNSAFE_INPUT_KEYWORDS:
        if kw in text:
            return False, f"输入包含敏感内容: {kw}"
    return True, ""


async def check_output_safety(text: str) -> tuple[bool, str]:
    """
    Check LLM output for safety. Returns (is_safe, reason).
    Uses Doubao moderation API if configured, otherwise uses keyword-based fallback.
    """
    result = await _doubao_moderation(text)
    if result is not None:
        return result
    for kw in _UNSAFE_OUTPUT_KEYWORDS:
        if kw in text:
            return False, "输出包含敏感内容"
    return True, ""
