"""Public decision experience: show the operation the user actually authorizes."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import AgentEvent, EventType
from ragcommerce_api.demo import create_demo_app
from ragcommerce_api.service import public_event

ROOT = Path(__file__).resolve().parents[3]
USER = "00000000-0000-5000-8000-000000000301"
HEADERS = {"X-User-ID": USER}


def test_task_history_rename_archive_and_conversation_are_owner_scoped():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    created = client.post(
        "/v1/threads", headers=HEADERS, json={"goal": "预算1000元通勤耳机"}
    ).json()
    tid = created["thread_id"]
    history = client.get("/v1/threads", headers=HEADERS)
    assert history.status_code == 200
    assert history.json()[0]["thread_id"] == tid
    assert (
        client.patch(
            f"/v1/threads/{tid}", headers=HEADERS, json={"title": "通勤候选", "archived": True}
        ).status_code
        == 200
    )
    assert client.get("/v1/threads", headers=HEADERS).json()[0]["experience"]["archived"] is True
    client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "history-1"},
        json={"text": "预算1000元通勤耳机"},
    )
    messages = client.get(f"/v1/threads/{tid}/messages", headers=HEADERS)
    assert messages.status_code == 200
    assert any(m["role"] == "user" and m["text"] == "预算1000元通勤耳机" for m in messages.json())
    assert any(m["role"] == "assistant" for m in messages.json())
    other = {"X-User-ID": str(uuid4())}
    assert client.get("/v1/threads", headers=other).json() == []
    assert client.get(f"/v1/threads/{tid}/messages", headers=other).status_code == 404
    assert (
        client.patch(f"/v1/threads/{tid}", headers=other, json={"archived": False}).status_code
        == 404
    )


def test_single_product_feedback_is_durable_reversible_and_does_not_exclude_category():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    tid = client.post("/v1/threads", headers=HEADERS, json={"goal": "预算1000元通勤耳机"}).json()[
        "thread_id"
    ]
    client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "feedback-1"},
        json={"text": "预算1000元通勤耳机"},
    )
    before = client.get(f"/v1/threads/{tid}", headers=HEADERS).json()
    pid = before["candidates"][0]["product_id"]
    request = {
        "product_id": pid,
        "expected_mission_version": before["mission"]["version"],
        "reason": "太重，仍保留续航要求",  # noqa: RUF001
    }
    response = client.patch(f"/v1/threads/{tid}/feedback", headers=HEADERS, json=request)
    assert response.status_code == 200
    assert response.json()["experience"]["feedback"] == {f"PRODUCT:{pid}": request["reason"]}
    client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "feedback-2"},
        json={"text": "预算1000元通勤耳机"},
    )
    after = client.get(f"/v1/threads/{tid}", headers=HEADERS).json()
    assert after["candidates"]
    assert pid not in [p["product_id"] for p in after["candidates"]]
    request.update(undo=True, expected_mission_version=after["mission"]["version"])
    assert (
        client.patch(f"/v1/threads/{tid}/feedback", headers=HEADERS, json=request).json()[
            "experience"
        ]["feedback"]
        == {}
    )


def test_category_feedback_undo_requires_owner_and_current_version():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    tid = client.post("/v1/threads", headers=HEADERS, json={"goal": "预算1000元通勤耳机"}).json()[
        "thread_id"
    ]
    client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "category-1"},
        json={"text": "预算1000元通勤耳机"},
    )
    snapshot = client.get(f"/v1/threads/{tid}", headers=HEADERS).json()
    response = client.patch(
        f"/v1/threads/{tid}/feedback",
        headers=HEADERS,
        json={
            "product_id": snapshot["candidates"][0]["product_id"],
            "expected_mission_version": snapshot["mission"]["version"],
            "scope": "CATEGORY",
            "reason": "不再看耳机",
        },
    )
    updated = response.json()
    key = next(iter(updated["experience"]["feedback"]))
    version = updated["mission"]["version"]
    assert (
        client.delete(
            f"/v1/threads/{tid}/feedback/{key}?version={version - 1}", headers=HEADERS
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/v1/threads/{tid}/feedback/{key}?version={version}",
            headers={"X-User-ID": str(uuid4())},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/v1/threads/{tid}/feedback/{key}?version={version}", headers=HEADERS
        ).json()["experience"]["feedback"]
        == {}
    )


def test_not_buying_is_a_persisted_success_without_commercial_writes():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    tid = client.post("/v1/threads", headers=HEADERS, json={"goal": "随便看看"}).json()["thread_id"]
    client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "explore-start"},
        json={"exploration_action": {"kind": "start"}, "expected_mission_version": 1},
    )
    version = client.get(f"/v1/threads/{tid}", headers=HEADERS).json()["mission"]["version"]
    ended = client.post(
        f"/v1/threads/{tid}/turns",
        headers={**HEADERS, "Idempotency-Key": "explore-end"},
        json={
            "exploration_action": {"kind": "end", "outcome": "USE_EXISTING"},
            "expected_mission_version": version,
        },
    )
    assert ended.status_code == 202
    result = client.get(f"/v1/threads/{tid}", headers=HEADERS).json()
    assert result["exploration"]["ended"] and result["exploration"]["outcome"] == "USE_EXISTING"
    assert result["status"] == "COMPLETED"
    assert client.get("/v1/cart", headers=HEADERS).json()["items"] == []
    assert client.get("/v1/lists", headers=HEADERS).json()["lists"] == []


def test_approval_public_event_preserves_exact_validated_operation():
    offer_id = str(uuid4())
    event = AgentEvent(
        1,
        EventType.APPROVAL_REQUIRED,
        uuid4(),
        {
            "tool": "cart.update",
            "reason": "explicit approval",
            "arguments": {"operation": "set", "offer_id": offer_id, "quantity": 2},
        },
    )
    name, payload = public_event(event)
    assert name == "approval_required"
    assert payload["arguments"] == {"operation": "set", "offer_id": offer_id, "quantity": 2}
