import pytest
pytestmark = pytest.mark.integration

"""Voice API contract tests."""
import json
import uuid

import pytest

from app.schemas.sse_events import DoneEvent, ProductCardEvent, ProgressEvent, TextDeltaEvent


def _parse_sse(raw: str) -> list[dict]:
    events = []
    current = {"event": None, "data": ""}
    for line in raw.splitlines():
        if line.startswith("event: "):
            current["event"] = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            current["data"] += line.removeprefix("data: ")
        elif not line and current["data"]:
            events.append({"event": current["event"], "data": json.loads(current["data"])})
            current = {"event": None, "data": ""}
    return events


@pytest.mark.asyncio
async def test_voice_recognize_returns_text(client, monkeypatch):
    from app.api import voice

    async def fake_recognize_voice(audio_bytes: bytes, filename: str):
        assert audio_bytes == b"audio"
        assert filename == "voice.m4a"
        return {"text": "推荐一款降噪耳机", "provider": "doubao_chat_input_audio"}

    monkeypatch.setattr(voice, "recognize_voice", fake_recognize_voice)
    response = await client.post(
        "/api/v1/voice/recognize",
        files={"file": ("voice.m4a", b"audio", "audio/mp4")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["text"] == "推荐一款降噪耳机"
    assert body["data"]["provider"] == "doubao_chat_input_audio"


@pytest.mark.asyncio
async def test_voice_chat_recognizes_then_streams_rag(client, monkeypatch):
    from app.api import voice

    session_id = str(uuid.uuid4())
    saved = []

    async def fake_get_or_create_session(_conversation_id=None):
        return session_id, {}

    async def fake_recognize_voice(_audio_bytes: bytes, _filename: str):
        return {"text": "推荐一款跑步耳机", "provider": "doubao_chat_input_audio"}

    async def fake_save_message(*args, **kwargs):
        saved.append((args, kwargs))

    async def fake_increment(_session_id: str):
        return None

    async def fake_generate_response(*_args, **_kwargs):
        yield {"event": "progress", "data": ProgressEvent(message="正在检索").model_dump_json()}
        yield {"event": "text_delta", "data": TextDeltaEvent(content="推荐理由").model_dump_json()}
        yield {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=str(uuid.uuid4()),
                title="测试耳机",
                price=299,
                index=1,
                total=1,
            ).model_dump_json(),
        }
        yield {"event": "done", "data": DoneEvent(total_cards=1).model_dump_json()}

    monkeypatch.setattr(voice, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(voice, "recognize_voice", fake_recognize_voice)
    monkeypatch.setattr(voice, "save_message", fake_save_message)
    monkeypatch.setattr(voice, "increment_message_count", fake_increment)
    monkeypatch.setattr(voice, "generate_response", fake_generate_response)

    response = await client.post(
        "/api/v1/voice/chat",
        files={"file": ("voice.m4a", b"audio", "audio/mp4")},
        data={"conversation_id": session_id, "cart_session_id": "cart-1", "user_id": "u1"},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [e["event"] for e in events] == [
        "progress",
        "voice_recognized",
        "progress",
        "text_delta",
        "product_cards",
        "done",
    ]
    assert events[1]["data"]["text"] == "推荐一款跑步耳机"
    assert saved[0][0][:3] == (session_id, "user", "推荐一款跑步耳机")
    assert saved[0][1]["audio_data"] == b"audio"
