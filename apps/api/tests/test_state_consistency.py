"""Regression cases from the 2026-10-02 code-level state audit."""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from ragcommerce_api.demo import DemoCommerce, create_demo_app

CATALOG = Path(__file__).resolve().parents[3] / "data/demo/catalog.v3.jsonl"
HEADERS = {"X-User-ID": "00000000-0000-5000-8000-000000000301"}


def create_thread(client, goal):
    return client.post("/v1/threads", json={"goal": goal}, headers=HEADERS).json()["thread_id"]


def submit(client, thread, key, text):
    return client.post(
        f"/v1/threads/{thread}/turns",
        json={"text": text, "media_ids": []},
        headers={**HEADERS, "Idempotency-Key": key},
    )


def test_clarification_replay_and_conflict_do_not_mutate_mission():
    client = TestClient(create_demo_app(CATALOG))
    thread = create_thread(client, "通勤耳机")
    assert submit(client, thread, "initial", "通勤耳机").status_code == 202
    path = f"/v1/threads/{thread}"
    before = client.get(path, headers=HEADERS).json()
    assert before["status"] == "WAITING_CLARIFICATION"
    assert submit(client, thread, "initial", "通勤耳机").status_code == 202
    assert client.get(path, headers=HEADERS).json() == before
    assert submit(client, thread, "initial", "预算 500 元").status_code == 409
    assert client.get(path, headers=HEADERS).json() == before
    assert submit(client, thread, "answer", "预算 1000 元").status_code == 202
    answered = client.get(path, headers=HEADERS).json()
    assert answered["mission"]["version"] == before["mission"]["version"] + 1
    assert "通勤耳机" in answered["goal"] and "1000" in answered["goal"]
    assert submit(client, thread, "answer", "预算 1000 元").status_code == 202
    assert client.get(path, headers=HEADERS).json() == answered


def test_edit_hides_old_candidates_and_rejects_old_comparison():
    client = TestClient(create_demo_app(CATALOG))
    thread = create_thread(client, "预算 1000 元的耳机")
    assert submit(client, thread, "first", "预算 1000 元的耳机").status_code == 202
    path = f"/v1/threads/{thread}"
    old = client.get(path, headers=HEADERS).json()
    selected = [old["candidates"][0]["product_id"]]
    assert (
        client.put(
            path + "/comparison", json={"product_ids": selected}, headers=HEADERS
        ).status_code
        == 200
    )
    edited = client.patch(
        path + "/constraints", json={"goal": "预算 5000 元的手机"}, headers=HEADERS
    )
    assert edited.status_code == 200
    current = client.get(path, headers=HEADERS).json()
    assert current["status"] == "IDLE"
    assert (
        current["candidates"]
        == current["recommendation_routes"]
        == current["selected_product_ids"]
        == []
    )
    assert (
        client.put(
            path + "/comparison", json={"product_ids": selected}, headers=HEADERS
        ).status_code
        == 422
    )


def test_invalid_catalog_references_cannot_enter_user_state():
    client = TestClient(create_demo_app(CATALOG))
    unknown = str(uuid4())
    response = client.post(
        "/v1/cart", json={"operation": "add", "offer_id": unknown, "quantity": 1}, headers=HEADERS
    )
    assert response.status_code == 404
    assert client.get("/v1/cart", headers=HEADERS).json()["items"] == []
    saved = client.post("/v1/lists", json={"name": "Original"}, headers=HEADERS).json()
    response = client.patch(
        f"/v1/lists/{saved['list_id']}",
        json={"name": "Changed", "add_variant_id": unknown},
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert client.get("/v1/lists", headers=HEADERS).json()["lists"] == [saved]


def test_watcher_threshold_updates_same_draft():
    from ragcommerce_contracts import CreateWatcherRequest

    commerce = DemoCommerce(CATALOG)
    user, thread = UUID(HEADERS["X-User-ID"]), uuid4()
    request = CreateWatcherRequest(
        kind="PRICE_BELOW", offer_id=next(iter(commerce.offers)), threshold_minor=50000
    )
    first = commerce.create_watcher(user, thread, request)
    updated = commerce.create_watcher(
        user, thread, request.model_copy(update={"threshold_minor": 40000})
    )
    assert updated.watcher_id == first.watcher_id
    assert updated.created_at == first.created_at
    assert updated.threshold_minor == 40000
    assert commerce.get_watchers(user, thread).watchers == [updated]


def test_snapshot_replaces_products_and_clears_finished_approval():
    from ragcommerce_agent_runtime import AgentEvent, EventType, TurnCommand
    from ragcommerce_api.media import InMemoryMediaStore
    from ragcommerce_api.service import TurnRecord, TurnService

    class ReplayAgent:
        def __init__(self):
            self.events = []

        def replay(self, run_id):
            return tuple(self.events)

    agent = ReplayAgent()
    service = TurnService(agent, InMemoryMediaStore())
    user, run = UUID(HEADERS["X-User-ID"]), uuid4()
    thread = service.create_thread(user, "耳机")
    service.index.reserve(
        TurnRecord(
            user, thread.id, run, "key", "fingerprint", TurnCommand(user, thread.id, run, "key")
        )
    )
    rows = [
        {key: row[key] for key in ("product_id", "variant_id", "title", "evidence_refs")}
        for row in list(DemoCommerce(CATALOG).rows.values())[:2]
    ]
    agent.events = [
        AgentEvent(1, EventType.PRODUCTS, run, {"products": [rows[0]]}),
        AgentEvent(2, EventType.PRODUCTS, run, {"products": [rows[1]]}),
        AgentEvent(3, EventType.APPROVAL_REQUIRED, run, {"tool": "cart.update"}),
    ]
    pending = service.snapshot(user, thread.id)
    assert [item.product_id for item in pending.candidates] == [UUID(rows[1]["product_id"])]
    assert pending.pending_action == "cart.update"
    service.update_comparison_selection(user, thread.id, [UUID(rows[1]["product_id"])])
    import pytest

    with pytest.raises(ValueError):
        service.update_comparison_selection(user, thread.id, [UUID(rows[0]["product_id"])])
    agent.events.append(AgentEvent(4, EventType.COMPLETED, run, {}))
    assert service.snapshot(user, thread.id).pending_action is None


def test_old_mission_approval_cannot_execute_after_edit():
    import asyncio

    import pytest
    from ragcommerce_agent_runtime import AgentEvent, EventType, TurnCommand
    from ragcommerce_api.media import InMemoryMediaStore
    from ragcommerce_api.service import DecisionConflict, TurnRecord, TurnService

    user, run = UUID(HEADERS["X-User-ID"]), uuid4()

    class ApprovalAgent:
        def replay(self, run_id):
            return (AgentEvent(1, EventType.APPROVAL_REQUIRED, run, {"tool": "cart.update"}),)

        def handle(self, command):
            raise AssertionError("stale approval must not execute any tool")

    service = TurnService(ApprovalAgent(), InMemoryMediaStore())
    thread = service.create_thread(user, "old task")
    service.index.reserve(
        TurnRecord(user, thread.id, run, "key", "body", TurnCommand(user, thread.id, run, "key"))
    )
    service.index.update_status(run, "WAITING_APPROVAL")
    service.update_mission(user, thread.id, "new task")
    with pytest.raises(DecisionConflict, match="earlier Mission"):
        asyncio.run(service.decide(user, run, "cart.update", True))
