from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from ragcommerce_agent_runtime import (
    FROZEN_TOOL_TYPES,
    PostgresCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolEvidence,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    TurnCommand,
)

pytestmark = pytest.mark.integration
IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-v1", "p1", "policy1", "0.1.0")


def database_url() -> str:
    value = os.environ.get("AGENT_DATABASE_URL")
    if not value:
        pytest.skip("AGENT_DATABASE_URL is required for Agent integration")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def command() -> TurnCommand:
    return TurnCommand(
        user_id=uuid4(),
        thread_id=uuid4(),
        run_id=uuid4(),
        idempotency_key="agent-postgres-replay-1",
        text="find a fixture product",
    )


def collect(agent: ShoppingAgent, turn: TurnCommand) -> list:
    async def run() -> list:
        return [event async for event in agent.handle(turn)]

    return asyncio.run(run())


def prepare_thread(turn: TurnCommand) -> None:
    mission_id = uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(database_url()) as connection:
        connection.execute(
            """INSERT INTO shopping_missions(
            id,user_ref,goal,budget_minor,currency,hard_constraints,exclusions,
            consented_preferences,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                mission_id,
                f"test-user-{turn.user_id}",
                "fixture mission",
                None,
                None,
                Jsonb([]),
                Jsonb([]),
                Jsonb([]),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO conversations(id,mission_id,created_at) VALUES (%s,%s,%s)",
            (turn.thread_id, mission_id, now),
        )


def test_postgres_checkpoint_replays_without_repeating_completed_tool() -> None:
    calls = 0

    def counted(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(
            {"title": "fixture"},
            (ToolEvidence("seed:fixture", "0" * 64, ("title",)),),
            frozenset({"title"}),
        )

    handlers: dict[str, Callable[[ToolExecutionContext, BaseModel], ToolResult]] = {
        name: counted for name in FROZEN_TOOL_TYPES
    }
    turn = command()
    prepare_thread(turn)
    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    first_agent = ShoppingAgent(
        planner, ToolRegistry(handlers), PostgresCheckpointStore(database_url()), IDENTITY
    )
    replay_agent = ShoppingAgent(
        planner, ToolRegistry(handlers), PostgresCheckpointStore(database_url()), IDENTITY
    )

    first = collect(first_agent, turn)
    replay = collect(replay_agent, turn)

    assert calls == 1
    assert [(event.id, event.type) for event in replay] == [
        (event.id, event.type) for event in first
    ]
    with psycopg.connect(database_url()) as connection:
        assert connection.execute(
            "SELECT status FROM agent_runs WHERE id = %s", (turn.run_id,)
        ).fetchone() == ("COMPLETED",)
        assert connection.execute(
            "SELECT count(*) FROM agent_steps WHERE run_id = %s", (turn.run_id,)
        ).fetchone() == (len(first),)
        assert connection.execute(
            """SELECT count(*) FROM tool_invocations ti JOIN agent_steps s ON s.id=ti.step_id
            WHERE s.run_id = %s AND ti.status = 'SUCCEEDED'""",
            (turn.run_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM evidence_refs WHERE run_id = %s", (turn.run_id,)
        ).fetchone() == (1,)


def test_postgres_preferences_require_consent_and_support_verified_deletion() -> None:
    store = PostgresCheckpointStore(database_url())
    agent = ShoppingAgent(
        ScriptedPlanner(()),
        ToolRegistry({name: (lambda _context, _args: ToolResult()) for name in FROZEN_TOOL_TYPES}),
        store,
        IDENTITY,
    )
    turn = command()

    assert agent.remember_preferences(turn, {"color": "black"}) is False
    assert store.delete_user(turn.user_id) == 0

    consented = TurnCommand(
        user_id=turn.user_id,
        thread_id=turn.thread_id,
        run_id=uuid4(),
        idempotency_key="agent-postgres-preference-1",
        text="remember black",
        consent_preference_memory=True,
    )
    assert agent.remember_preferences(consented, {"color": "black"}) is True
    assert agent.load_preferences(turn.user_id) == {"color": "black"}
    assert store.delete_user(turn.user_id) == 1
    assert store.delete_user(turn.user_id) == 0
