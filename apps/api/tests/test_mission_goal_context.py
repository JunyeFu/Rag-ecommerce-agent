from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import (
    InMemoryCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolRegistry,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.demo import DemoCommerce
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.service import TurnService, public_event


def test_followup_action_does_not_replace_the_shopping_goal_or_budget():
    media = InMemoryMediaStore()
    commerce = DemoCommerce(Path(__file__).resolve().parents[3] / "data/demo/catalog.v3.jsonl")
    agent = ShoppingAgent(
        ScriptedPlanner(()),
        ToolRegistry(commerce.tool_handlers()),
        InMemoryCheckpointStore(),
        RuntimeIdentity("test", "fake", "test", "test", "0.2.0"),
    )
    client = TestClient(create_app(TurnService(agent, media), media))
    headers = {"X-User-ID": "00000000-0000-5000-8000-000000000762"}
    goal = "预算2000元的通勤手机"
    thread = client.post("/v1/threads", headers=headers, json={"goal": goal}).json()
    accepted = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        headers={**headers, "Idempotency-Key": "goal-context-action"},
        json={"text": "请将已选报价以数量2加入待购", "media_ids": []},
    ).json()
    snapshot = client.get(f"/v1/threads/{thread['thread_id']}", headers=headers).json()
    assert snapshot["goal"] == goal
    assert snapshot["mission"]["goal"] == goal
    assert snapshot["mission"]["budget_total_minor"] == 200000
    assert snapshot["mission"]["unknowns"] == []
    events = client.get(f"/v1/agent-runs/{accepted['run_id']}/events", headers=headers).text
    assert '"budget_total_minor":200000' in events.replace(" ", "")


def test_invalid_mission_event_is_not_projected_as_an_empty_success():
    from ragcommerce_agent_runtime import AgentEvent, EventType

    event = AgentEvent(
        1, EventType.MISSION_UPDATED, uuid4(), {"goal": "shopping", "status": "IN_PROGRESS"}
    )
    with pytest.raises(KeyError, match="mission"):
        public_event(event)
