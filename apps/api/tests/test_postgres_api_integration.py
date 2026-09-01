from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
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
from ragcommerce_worker import TurnWorker

pytestmark = pytest.mark.integration
IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-api-v1", "p1", "policy1", "0.2.0")


def database_url() -> str:
    value = os.environ.get("API_DATABASE_URL")
    if not value:
        pytest.skip("API_DATABASE_URL is required for API integration")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def submit(service: TurnService, owner_id: UUID, thread_id: UUID):
    async def submit_and_execute():
        record, replayed = await service.submit(owner_id, thread_id, "api-restart-1", "fixture", ())
        if not replayed:
            record = await service.execute(record.run_id)
        return record, replayed

    return asyncio.run(submit_and_execute())


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


def test_concurrent_workers_claim_once_and_emit_one_terminal_event() -> None:
    def search(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult()

    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    index = PostgresTurnIndex(database_url())
    service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(database_url()),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        index,
    )
    owner_id = uuid4()
    thread = service.create_thread(owner_id, "concurrent claim fixture")

    async def reserve():
        return await service.submit(owner_id, thread.id, "claim-once-1", "fixture", ())

    pending, replayed = asyncio.run(reserve())
    assert replayed is False
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = tuple(pool.map(lambda _: index.claim_next(), range(2)))
    claimed = [record for record in claims if record is not None]

    assert [record.run_id for record in claimed] == [pending.run_id]
    asyncio.run(service.execute_claimed(claimed[0]))
    loaded = service.require_run(owner_id, pending.run_id)
    terminal = [
        event.type.value for event in loaded.events if event.type.value in {"completed", "failed"}
    ]

    assert terminal == ["completed"]


def test_stale_worker_claim_is_recovered_after_restart() -> None:
    def search(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult()

    dsn = database_url()
    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    index = PostgresTurnIndex(dsn)
    service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        index,
    )
    owner_id = uuid4()
    thread = service.create_thread(owner_id, "worker restart fixture")

    async def reserve():
        return await service.submit(owner_id, thread.id, "worker-restart-1", "fixture", ())

    pending, replayed = asyncio.run(reserve())
    assert replayed is False
    abandoned = index.claim_next()
    assert abandoned is not None and abandoned.run_id == pending.run_id
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE api_turns SET claimed_at=NOW() - INTERVAL '6 minutes' WHERE run_id=%s",
            (pending.run_id,),
        )

    restarted_index = PostgresTurnIndex(dsn)
    restarted_service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        restarted_index,
    )
    assert asyncio.run(TurnWorker(restarted_index, restarted_service).run_once()) is True
    assert asyncio.run(TurnWorker(restarted_index, restarted_service).run_once()) is False
    loaded = restarted_service.require_run(owner_id, pending.run_id)
    terminal = [
        event.type.value for event in loaded.events if event.type.value in {"completed", "failed"}
    ]
    assert terminal == ["completed"]
