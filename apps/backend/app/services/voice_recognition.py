"""
Voice recognition via LLM multimodal chat with fallback transcription.
"""
import base64
import io
import logging
from pathlib import Path

from app.core.config import settings
from app.services.llm_client import create_llm_client

logger = logging.getLogger("voice_recognition")


def _audio_format(filename: str) -> str:
    suffix = Path(filename or "voice.m4a").suffix.lower().lstrip(".")
    if suffix in {"m4a", "mp4", "aac"}:
        return "m4a"
    if suffix in {"wav", "mp3", "ogg", "opus", "flac"}:
        return suffix
    return "m4a"


def _needs_thinking_disabled() -> bool:
    base = (settings.DOUBAO_BASE_URL or settings.DEEPSEEK_BASE_URL or "").lower()
    return "volces.com" in base or "xiaomimimo.com" in base


async def _recognize_with_multimodal(audio_bytes: bytes, filename: str) -> str:
    client = create_llm_client(timeout=45.0)
    fmt = _audio_format(filename)
    encoded = base64.b64encode(audio_bytes).decode("ascii")

    extra_kwargs = {}
    if _needs_thinking_disabled():
        extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是中文语音转写器。只输出用户语音的完整转写文本，不要解释。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请转写这段语音，保留购物需求中的品牌、价格、数量和约束。"},
                    {"type": "input_audio", "input_audio": {"data": encoded, "format": fmt}},
                ],
            },
        ],
        temperature=0,
        max_tokens=300,
        **extra_kwargs,
    )
    return (response.choices[0].message.content or "").strip()


async def _recognize_with_whisper(audio_bytes: bytes, filename: str) -> str:
    client = create_llm_client(timeout=60.0)
    file_tuple = (filename or "voice.m4a", io.BytesIO(audio_bytes), "audio/mp4")
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=file_tuple,
        response_format="json",
    )
    return (getattr(response, "text", "") or "").strip()


async def recognize_voice(audio_bytes: bytes, filename: str = "voice.m4a") -> dict:
    if not audio_bytes:
        raise RuntimeError("Audio file is empty")

    errors: list[str] = []
    try:
        text = await _recognize_with_multimodal(audio_bytes, filename)
        if text:
            return {"text": text, "provider": "multimodal_llm"}
    except Exception as exc:
        logger.warning("Multimodal voice recognition failed: %s", exc)
        errors.append(f"multimodal: {str(exc)[:120]}")

    try:
        text = await _recognize_with_whisper(audio_bytes, filename)
        if text:
            return {"text": text, "provider": "whisper-1"}
    except Exception as exc:
        logger.warning("whisper-1 fallback failed: %s", exc)
        errors.append(f"whisper-1: {str(exc)[:120]}")

    raise RuntimeError("; ".join(errors) or "No speech recognized")
