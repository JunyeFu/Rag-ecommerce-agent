import pytest
pytestmark = pytest.mark.integration

"""Chat SSE contract tests."""
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
async def test_chat_stream_contract_with_product_card(client, monkeypatch):
    """聊天端点应按 progress -> text_delta -> product_cards -> done 输出 SSE。"""
    from app.api import chat as chat_api

    async def fake_get_or_create_session(_conversation_id=None):
        return str(uuid.uuid4()), {}

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_generate_response(*_args, **_kwargs):
        yield {"event": "progress", "data": ProgressEvent(message="正在分析").model_dump_json()}
        yield {"event": "text_delta", "data": TextDeltaEvent(content="推荐理由").model_dump_json()}
        yield {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=str(uuid.uuid4()),
                title="测试耳机",
                price=199,
                index=1,
                total=1,
            ).model_dump_json(),
        }
        yield {"event": "done", "data": DoneEvent(total_cards=1, latency_ms=12).model_dump_json()}

    monkeypatch.setattr(chat_api, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(chat_api, "save_message", fake_noop)
    monkeypatch.setattr(chat_api, "increment_message_count", fake_noop)
    monkeypatch.setattr(chat_api, "generate_response", fake_generate_response)

    response = await client.post("/api/v1/chat", json={"message": "推荐耳机"})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    events = _parse_sse(response.text)
    assert [e["event"] for e in events] == ["progress", "text_delta", "product_cards", "done"]
    assert events[2]["data"]["title"] == "测试耳机"
    assert events[-1]["data"]["total_cards"] == 1


def test_stream_marker_cleanup():
    from app.services.agent import _clean_stream_text

    assert _clean_stream_text("[SUMMARY]开头[PRODUCT_1]商品[CLOSING]结尾") == "开头商品结尾"
