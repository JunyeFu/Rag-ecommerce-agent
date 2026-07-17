"""
Image understanding for product search.

Uses the configured LLM provider's vision API (OpenAI-compatible format).
Local vision models are intentionally not loaded here, so mobile startup
and backend deployments do not depend on heavyweight local model files.
"""
import asyncio
import base64
import json
import logging
import re
import time
import uuid
from pathlib import Path

logger = logging.getLogger("image_parser")

_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        from app.services.llm_client import create_llm_client

        _llm_client = create_llm_client()
    return _llm_client


UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _api_key_configured() -> bool:
    from app.core.config import settings
    return bool(settings.DOUBAO_API_KEY or settings.DEEPSEEK_API_KEY)


def get_vision_readiness() -> dict:
    """Return vision API readiness details."""
    return {
        "provider": "llm_vision_api",
        "cloud_vision_configured": _api_key_configured(),
        "ready": _api_key_configured(),
    }


def _needs_thinking_disabled() -> bool:
    """Doubao and Mimo need explicit thinking=disabled for vision calls."""
    from app.core.config import settings
    base = (settings.DOUBAO_BASE_URL or settings.DEEPSEEK_BASE_URL or "").lower()
    return "volces.com" in base or "xiaomimimo.com" in base


async def _parse_with_vision(image_bytes: bytes) -> dict:
    """Parse a product image using the configured LLM vision API (OpenAI-compatible)."""
    from app.core.config import settings

    if not _api_key_configured():
        raise RuntimeError("No API key configured for vision (set DOUBAO_API_KEY or DEEPSEEK_API_KEY)")

    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{img_b64}"
    prompt = _build_prompt()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    client = _get_llm_client()
    start = time.time()

    extra_kwargs = {}
    if _needs_thinking_disabled():
        extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=256,
        **extra_kwargs,
    )

    elapsed = time.time() - start
    output_text = resp.choices[0].message.content or ""
    logger.info("Vision parsed in %.1fs: %s...", elapsed, output_text[:80])

    result = _parse_vlm_output(output_text)
    if result["confidence"] == 0.0:
        result["confidence"] = 0.3
    return result


async def parse_product_image(image_bytes: bytes) -> dict:
    """
    Extract structured product attributes from an image through vision API.

    Returns:
        {category, brand, color, material, style, keywords, description, confidence}
    """
    try:
        return await _parse_with_vision(image_bytes)
    except Exception as e:
        logger.error("Vision API failed: %s", e)
        raise RuntimeError(f"Vision API failed: {str(e)[:100]}") from e


def _build_prompt() -> str:
    return """
You are an ecommerce product image analysis assistant. Analyze the product image
and extract the following fields:

1. category: concrete product category, such as sneakers, T-shirt, phone, earbuds
2. brand: visible brand logo or text
3. color: primary color
4. material: visible material features
5. style: design style
6. keywords: 3-5 ecommerce search keywords
7. description: one concise sentence within 25 Chinese characters

Return JSON only:
{"category": "...", "brand": "...", "color": "...", "material": "...", "style": "...", "keywords": [...], "description": "..."}
Use null when a field cannot be identified.
""".strip()


def _parse_vlm_output(text: str) -> dict:
    """Parse vision-model JSON output defensively."""
    default = {
        "category": None,
        "brand": None,
        "color": None,
        "material": None,
        "style": None,
        "keywords": [],
        "description": None,
        "confidence": 0.0,
    }

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            return default
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return default

    result = {**default}
    for key in default:
        if key in data and data[key] is not None and data[key] != "null":
            result[key] = data[key]

    if not isinstance(result["keywords"], list):
        result["keywords"] = [str(result["keywords"])]

    if not result["description"] and result["keywords"]:
        result["description"] = ", ".join(str(k) for k in result["keywords"][:3])

    non_null = sum(
        1
        for key in ["category", "brand", "color", "material", "style", "description"]
        if result.get(key)
    )
    result["confidence"] = round(non_null / 6, 2) if non_null > 0 else 0.0
    return result


async def parse_product_image_from_path(image_path: str) -> dict:
    """Read an image from disk without blocking the event loop, then parse it."""
    data = await asyncio.to_thread(lambda: Path(image_path).read_bytes())
    return await parse_product_image(data)


def save_upload_image(image_bytes: bytes, filename: str) -> str:
    """Save an uploaded image and return its absolute file path."""
    ext = Path(filename).suffix or ".jpg"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / safe_name
    filepath.write_bytes(image_bytes)
    logger.info("Image saved: %s", filepath)
    return str(filepath)
