"""Voice input APIs: audio recognition and voice-to-RAG SSE chat."""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.schemas.common import ApiResponse
from app.schemas.sse_events import DoneEvent, ErrorEvent, ProgressEvent
from app.services.agent import generate_response
from app.services.state_manager import get_or_create_session, increment_message_count, save_message
from app.services.voice_recognition import recognize_voice

logger = logging.getLogger("voice_api")
router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024


async def _read_audio(file: UploadFile) -> tuple[bytes, str]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Audio file is empty")
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio size exceeds 25MB")
    return contents, file.filename or "voice.m4a"


@router.post("/voice/recognize")
async def recognize(file: UploadFile = File(...)):
    audio_bytes, filename = await _read_audio(file)
    try:
        result = await recognize_voice(audio_bytes, filename)
    except Exception as exc:
        logger.error("Voice recognition failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Voice recognition failed: {str(exc)[:120]}") from exc
    return ApiResponse(data=result, message="Voice recognized")


@router.post("/voice/chat")
async def voice_chat(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    cart_session_id: str | None = Form(default=None),
    user_id: str = Form(default=""),
):
    audio_bytes, filename = await _read_audio(file)
    session_id, state = await get_or_create_session(conversation_id)
    runtime_state = dict(state or {})
    if cart_session_id:
        runtime_state["cart_session_id"] = cart_session_id
    if user_id:
        runtime_state["user_id"] = user_id

    async def event_generator():
        response_text_parts: list[str] = []
        try:
            yield {"event": "progress", "data": ProgressEvent(message="正在理解语音...").model_dump_json()}
            recognized = await recognize_voice(audio_bytes, filename)
            text = recognized["text"].strip()
            if not text:
                raise RuntimeError("No speech recognized")

            yield {
                "event": "voice_recognized",
                "data": json.dumps(
                    {
                        "type": "voice_recognized",
                        "text": text,
                        "provider": recognized.get("provider", ""),
                    },
                    ensure_ascii=False,
                ),
            }
            await save_message(session_id, "user", text, audio_data=audio_bytes)

            async for event in generate_response(
                message=text,
                conversation_id=session_id,
                state=runtime_state,
            ):
                try:
                    data = json.loads(event.get("data", "{}"))
                    if data.get("type") == "text_delta":
                        response_text_parts.append(data.get("content", ""))
                except (json.JSONDecodeError, TypeError):
                    pass
                yield event

            await save_message(session_id, "assistant", "".join(response_text_parts))
            await increment_message_count(session_id)
        except Exception as exc:
            logger.exception("Voice chat endpoint error")
            error = ErrorEvent(message=f"语音导购失败: {str(exc)[:80]}", code="VOICE_CHAT_ERROR")
            yield {"event": "error", "data": error.model_dump_json()}
            yield {"event": "done", "data": DoneEvent().model_dump_json()}

    return EventSourceResponse(event_generator())
