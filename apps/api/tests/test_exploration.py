from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ragcommerce_api.demo import create_demo_app

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def session():
    app = create_demo_app(ROOT / "data/demo/catalog.v3.jsonl")
    client = TestClient(app)
    headers = {"X-User-ID": str(uuid4())}
    thread = client.post("/v1/threads", json={"goal": "随便看看"}, headers=headers).json()[
        "thread_id"
    ]
    return client, headers, thread


def snapshot(session):
    client, headers, thread = session
    return client.get(f"/v1/threads/{thread}", headers=headers).json()


def act(session, kind, *, key=None, version=None, **values):
    client, headers, thread = session
    return client.post(
        f"/v1/threads/{thread}/turns",
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json={
            "expected_mission_version": version or snapshot(session)["mission"]["version"],
            "exploration_action": {"kind": kind, **values},
        },
    )


def test_no_budget_exploration_feedback_exhaustion_and_undo(session):
    assert act(session, "start", experience_tags=["life_improvement", "novelty"]).status_code == 202
    first = snapshot(session)
    assert first["mode"] == "DISCOVERY" and first["mission"]["budget_total_minor"] is None
    directions = first["exploration"]["directions"]
    assert len(directions) == 3 and len({d["category"] for d in directions}) == 3
    assert {tag for d in directions for tag in d["experience_tags"]} == {
        "life_improvement",
        "novelty",
    }
    assert all(d["evidence_refs"] and d["supporting_product_ids"] for d in directions)
    assert all(d["scenario_hint"] and d["try_first"] and d["to_confirm"] for d in directions)
    excluded = directions[0]["direction_id"]
    assert (
        act(session, "feedback", direction_id=excluded, value="not_interested").status_code == 202
    )
    assert act(session, "select_for_purchase", direction_id=excluded).status_code == 422
    seen = {d["direction_id"] for d in directions}
    for _ in range(3):
        assert act(session, "next").status_code == 202
        page = snapshot(session)["exploration"]["directions"]
        assert not seen.intersection(d["direction_id"] for d in page)
        seen.update(d["direction_id"] for d in page)
    assert snapshot(session)["exploration"]["exhausted"]
    assert act(session, "feedback", direction_id=excluded, value="neutral").status_code == 202
    assert act(session, "next").status_code == 202
    assert snapshot(session)["exploration"]["directions"][0]["direction_id"] == excluded
    client, headers, _ = session
    assert client.get("/v1/cart", headers=headers).json()["items"] == []
    assert client.get("/v1/lists", headers=headers).json()["lists"] == []


def test_selection_clarifies_then_uses_same_purchase_agent(session):
    act(session, "start")
    before = snapshot(session)
    direction = before["exploration"]["directions"][0]
    act(session, "feedback", direction_id=direction["direction_id"], value="interested")
    response = act(session, "select_for_purchase", direction_id=direction["direction_id"])
    assert response.status_code == 202
    after = snapshot(session)
    assert after["mode"] == "PURCHASE" and after["status"] == "WAITING_CLARIFICATION"
    assert direction["category"] in after["goal"] and direction["title"] in after["goal"]
    assert after["selected_product_ids"] == [] and after["candidates"] == []
    client, headers, thread = session
    answer = client.post(
        f"/v1/threads/{thread}/turns",
        headers={**headers, "Idempotency-Key": "budget"},
        json={"text": "预算5000元"},
    )
    assert answer.status_code == 202
    result = snapshot(session)
    assert result["status"] == "COMPLETED" and result["candidates"]
    assert result["mission"]["budget_total_minor"] == 500000


def test_replay_precedes_version_check_and_changed_body_conflicts(session):
    first = act(session, "start", key="same", version=1)
    assert act(session, "start", key="same", version=1).json()["replayed"]
    assert snapshot(session)["mission"]["version"] == 2
    assert act(session, "next", key="same", version=1).status_code == 409
    assert act(session, "next", version=1).status_code == 409
    client, headers, _ = session
    events = client.get(f"/v1/agent-runs/{first.json()['run_id']}/events", headers=headers).text
    assert "event: exploration_updated" in events


def test_boundaries_forged_direction_owner_mixed_input_and_end(session):
    act(session, "start")
    assert act(session, "feedback", direction_id="invented", value="interested").status_code == 422
    client, headers, thread = session
    body = {"exploration_action": {"kind": "next"}, "expected_mission_version": 2}
    assert (
        client.post(
            f"/v1/threads/{thread}/turns",
            headers={**headers, "Idempotency-Key": "mixed"},
            json={**body, "text": "also buy"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/v1/threads/{thread}/turns",
            headers={"X-User-ID": str(uuid4()), "Idempotency-Key": "other"},
            json=body,
        ).status_code
        == 404
    )
    assert act(session, "end").status_code == 202
    assert snapshot(session)["exploration"]["ended"]
    assert act(session, "next").status_code == 422
    assert client.get("/v1/cart", headers=headers).json()["items"] == []


def test_exploration_invalidates_old_approval_without_erasing_saved_list(session):
    from ragcommerce_agent_runtime import ScriptedPlanner, ToolCall

    client, headers, thread = session
    service = client.app.state.turn_service
    commerce = client.app.state.commerce
    service.agent.planner = ScriptedPlanner(
        (
            ToolCall(
                "cart.update",
                {
                    "operation": "add",
                    "offer_id": str(next(iter(commerce.offers))),
                    "quantity": 1,
                },
            ),
        )
    )
    saved = client.post("/v1/lists", headers=headers, json={"name": "保留我的清单"}).json()
    pending = client.post(
        f"/v1/threads/{thread}/turns",
        headers={**headers, "Idempotency-Key": "old"},
        json={"text": "加入待购"},
    ).json()
    assert snapshot(session)["status"] == "WAITING_APPROVAL"
    assert act(session, "start").status_code == 202
    response = client.post(
        f"/v1/agent-runs/{pending['run_id']}/decisions",
        headers=headers,
        json={"tool_name": "cart.update", "approved": True},
    )
    assert response.status_code == 409
    assert snapshot(session)["pending_action"] is None
    assert client.get("/v1/cart", headers=headers).json()["items"] == []
    assert (
        client.get("/v1/lists", headers=headers).json()["lists"][0]["list_id"] == saved["list_id"]
    )


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "next", "direction_id": "x"},
        {"kind": "feedback"},
        {"kind": "select_for_purchase", "direction_id": "x", "value": "interested"},
        {"kind": "start", "experience_tags": ["novelty", "novelty"]},
        {"kind": "start", "experience_tags": ["made_up"]},
    ],
)
def test_invalid_action_is_explicit_422(session, action):
    client, headers, thread = session
    response = client.post(
        f"/v1/threads/{thread}/turns",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"exploration_action": action, "expected_mission_version": 1},
    )
    assert response.status_code == 422
    assert snapshot(session)["mission"]["version"] == 1
