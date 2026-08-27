from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from ragcommerce_agent_runtime import (
    FROZEN_TOOL_TYPES,
    PostgresCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
)
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.service import TurnService

pytestmark = pytest.mark.integration
IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-api-v1", "p1", "policy1", "0.1.0")


def database_url() -> str:
    value = os.environ.get("API_DATABASE_URL")
    if not value:
        pytest.skip("API_DATABASE_URL is required for API integration")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def submit(service: TurnService, owner_id: UUID, thread_id: UUID):
    return asyncio.run(service.submit(owner_id, thread_id, "api-restart-1", "fixture", ()))


def test_postgres_index_and_agent_events_survive_api_process_recreation() -> None:
    calls = 0

    def counted(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult()

    handlers: dict[str, Callable[[ToolExecutionContext, BaseModel], ToolResult]] = {
        name: counted for name in FROZEN_TOOL_TYPES
    }
    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    first_agent = ShoppingAgent(
        planner,
        ToolRegistry(handlers),
        PostgresCheckpointStore(database_url()),
        IDENTITY,
    )
    first = TurnService(first_agent, InMemoryMediaStore(), PostgresTurnIndex(database_url()))
    owner_id = uuid4()
    thread = first.create_thread(owner_id, "restart fixture")
    initial, replayed = submit(first, owner_id, thread.id)
    assert replayed is False
    assert calls == 1

    recreated_agent = ShoppingAgent(
        planner,
        ToolRegistry(handlers),
        PostgresCheckpointStore(database_url()),
        IDENTITY,
    )
    recreated = TurnService(
        recreated_agent, InMemoryMediaStore(), PostgresTurnIndex(database_url())
    )
    replay, replayed = submit(recreated, owner_id, thread.id)
    loaded = recreated.require_run(owner_id, initial.run_id)

    assert replayed is True
    assert calls == 1
    assert [event.id for event in replay.events] == [event.id for event in initial.events]
    assert [event.id for event in loaded.events] == [event.id for event in initial.events]
    assert loaded.events[-1].type.value == "completed"
