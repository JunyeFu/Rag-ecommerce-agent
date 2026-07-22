import pytest
pytestmark = pytest.mark.integration

"""
SSE event tests — 验证 SSE 事件流格式。DB-dependent tests use db_check fixture.
"""
import json
import pytest


def parse_sse_events(raw: str) -> list[dict]:
    """Parse SSE text into list of {event, data} dicts"""
    events = []
    current_event = None
    for line in raw.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                data = line[6:]
            events.append({"event": current_event or "message", "data": data})
            current_event = None
    return events


@pytest.mark.asyncio
async def test_chitchat_returns_progress_then_text(client):
    response = await client.post("/api/v1/chat", json={"message": "你好"})
    assert response.status_code == 200
    events = parse_sse_events(response.text)
    types = [e.get("data", {}).get("type") if isinstance(e.get("data"), dict) else e.get("event") for e in events]
    assert "progress" in types
    assert any(t in types for t in ("text_delta", "done"))

@pytest.mark.asyncio
async def test_done_event_structure(client, db_check):
    response = await client.post("/api/v1/chat", json={"message": "你好"})
    events = parse_sse_events(response.text)
    done_events = [e for e in events if isinstance(e.get("data"), dict) and e["data"].get("type") == "done"]
    assert len(done_events) >= 1
    done = done_events[-1]["data"]
    assert "total_cards" in done

@pytest.mark.asyncio
async def test_recommend_streams_correct_content_type(client, db_check):
    """推荐类查询应返回 SSE content-type"""
    resp = await client.post("/api/v1/chat", json={"message": "推荐轻量跑鞋"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    # Verify at least progress events are emitted
    assert "event: progress" in resp.text
