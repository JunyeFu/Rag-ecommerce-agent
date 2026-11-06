"""Media consent, server truth, confirmation idempotency and stale Mission regression."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from ragcommerce_api.demo import create_demo_app

ROOT = Path(__file__).resolve().parents[3]


def pending():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    user = str(uuid4())
    headers = {"X-User-ID": user}
    thread = client.post(
        "/v1/threads", json={"goal": "请识别我选中的商品"}, headers=headers
    ).json()["thread_id"]
    media = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82",
        headers={**headers, "Content-Type": "image/png"},
    ).json()["media_id"]
    run = client.post(
        f"/v1/threads/{thread}/turns",
        json={"media_ids": [media]},
        headers={**headers, "Idempotency-Key": "media-1"},
    ).json()["run_id"]
    return client, headers, thread, media, run


def test_invalid_media_schema_fails_with_redacted_field_diagnostic(monkeypatch):
    from uuid import UUID

    from ragcommerce_api.demo import DemoProvider

    async def invalid(self, *args):
        return {
            "recognized_text": "private user phrase",
            "category": "unsupported-category",
            "visible_attributes": [],
            "uncertainties": [],
            "supported": True,
        }

    monkeypatch.setattr(DemoProvider, "interpret_media", invalid)
    client, headers, thread, _, run = pending()
    snapshot = client.get(f"/v1/threads/{thread}", headers=headers).json()
    assert snapshot["status"] == "FAILED" and snapshot["pending_media_interpretations"] == []
    events = client.app.state.turn_service.agent.replay(UUID(run))
    failure = next(event for event in events if event.type == "tool_failed")
    assert failure.data["error_summary"] == "media schema: category:literal_error"
    assert "private user phrase" not in str(failure.data)


def test_media_understanding_waits_for_confirmation_and_survives_snapshot():
    client, headers, thread, media, run = pending()
    snapshot = client.get(f"/v1/threads/{thread}", headers=headers).json()
    assert snapshot["status"] == "WAITING_CLARIFICATION"
    assert snapshot["candidates"] == []
    assert snapshot["pending_media_interpretations"][0]["media_id"] == media
    events = client.get(f"/v1/agent-runs/{run}/events", headers=headers).text
    assert "event: media_interpreted" in events
    assert "event: products" not in events


def test_confirmation_updates_mission_once_and_uses_normal_agent_chain():
    client, headers, thread, _, run = pending()
    body = {
        "media_confirmation": {"source_run_id": run, "text": "通勤耳机, 预算800元"},
        "expected_mission_version": 1,
    }
    accepted = client.post(
        f"/v1/threads/{thread}/turns",
        json=body,
        headers={**headers, "Idempotency-Key": "confirm-1"},
    )
    assert accepted.status_code == 202
    replay = client.post(
        f"/v1/threads/{thread}/turns",
        json=body,
        headers={**headers, "Idempotency-Key": "confirm-1"},
    )
    assert replay.status_code == 202 and replay.json()["replayed"]
    snapshot = client.get(f"/v1/threads/{thread}", headers=headers).json()
    assert snapshot["mission"]["version"] == 2
    assert snapshot["pending_media_interpretations"] == []
    assert snapshot["candidates"] and snapshot["status"] == "COMPLETED"
    stale = client.post(
        f"/v1/threads/{thread}/turns",
        json=body,
        headers={**headers, "Idempotency-Key": "confirm-2"},
    )
    assert stale.status_code == 409


def test_other_user_cannot_read_or_confirm_media_and_mission_edit_invalidates_it():
    client, headers, thread, media, run = pending()
    other = {"X-User-ID": str(uuid4()), "Idempotency-Key": "other"}
    assert (
        client.post(
            f"/v1/threads/{thread}/turns", json={"media_ids": [media]}, headers=other
        ).status_code
        == 404
    )
    client.patch(
        f"/v1/threads/{thread}/constraints", json={"goal": "相机, 预算3000元"}, headers=headers
    )
    assert (
        client.post(
            f"/v1/threads/{thread}/turns",
            json={
                "media_confirmation": {"source_run_id": run, "text": "耳机"},
                "expected_mission_version": 1,
            },
            headers={**headers, "Idempotency-Key": "stale"},
        ).status_code
        == 409
    )
