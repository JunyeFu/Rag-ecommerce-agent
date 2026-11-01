from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from ragcommerce_api.ops import (
    EntityConflict,
    OpsActor,
    ResolveConflictRequest,
    StartEvaluationRequest,
)
from ragcommerce_api.postgres_ops import PostgresOpsStore

pytestmark = pytest.mark.integration


def database_url() -> str:
    value = os.environ.get("API_DATABASE_URL")
    if not value:
        pytest.skip("API_DATABASE_URL is required for API integration")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def test_ops_mutations_and_audit_survive_store_recreation() -> None:
    suffix = uuid4().hex
    actor = OpsActor(f"ops-restart-{suffix}", "reviewer")
    conflict_id = f"conflict-restart-{suffix}"
    store = PostgresOpsStore(database_url())
    store.conflicts[conflict_id] = EntityConflict(
        conflict_id=conflict_id,
        left_entity_ref="entity:test-left",
        right_entity_ref="entity:test-right",
        conflict_fields=["model_number"],
        confidence=0.8,
        status="PENDING",
        source_refs=["test:left", "test:right"],
        observed_at=datetime.now(UTC),
    )

    resolved = store.resolve_conflict(
        actor,
        conflict_id,
        ResolveConflictRequest(
            decision="KEEP_SEPARATE",
            reason="integration restart evidence",
        ),
        f"resolve-{suffix}",
    )
    queued = store.start_evaluation(
        actor,
        StartEvaluationRequest(
            dataset_version=f"v3-restart-{suffix}",
            runner_version="deterministic-2",
        ),
        f"evaluation-{suffix}",
    )

    recreated = PostgresOpsStore(database_url())

    assert resolved.status == "KEPT_SEPARATE"
    assert recreated.conflicts[conflict_id] == resolved
    assert any(run == queued for run in recreated.evaluations)
    audit = [event for event in recreated.audit if event.actor_ref == actor.ref]
    assert [event.action for event in audit] == [
        "entity_conflict.resolve",
        "evaluation.start",
    ]


def test_ops_trace_reads_current_agent_events_not_static_fixtures():
    from ragcommerce_agent_runtime import (
        PostgresCheckpointStore,
        RuntimeIdentity,
        ShoppingAgent,
        ToolRegistry,
    )
    from ragcommerce_api.demo import DemoProvider
    from ragcommerce_api.media import InMemoryMediaStore
    from ragcommerce_api.postgres_demo import PostgresDemoCommerce
    from ragcommerce_api.postgres_index import PostgresTurnIndex
    from ragcommerce_api.service import TurnService

    dsn = database_url()
    commerce = PostgresDemoCommerce(
        Path(__file__).resolve().parents[3] / "data/demo/catalog.v3.jsonl", dsn
    )
    provider = DemoProvider()
    agent = ShoppingAgent(
        provider,
        ToolRegistry(commerce.tool_handlers()),
        PostgresCheckpointStore(dsn),
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            "deterministic-demo",
            "p1",
            "commercial-truth-v3",
            "0.2.0",
            "fixture",
        ),
    )
    service = TurnService(agent, InMemoryMediaStore(), PostgresTurnIndex(dsn))
    owner = uuid4()
    goal = "预算800元的通勤降噪耳机"
    thread = service.create_thread(owner, goal)
    record, _ = asyncio.run(service.submit(owner, thread.id, uuid4().hex, goal, ()))
    # Execute this exact record, not a pre-existing job in the test database.
    claimed = service.index.claim(record.run_id)
    asyncio.run(service.execute_claimed(claimed))
    traces = PostgresOpsStore(dsn).list_traces()
    trace = next(item for item in traces if item.run_id == str(record.run_id))
    assert trace.status == "COMPLETED"
    assert trace.model_version == "deterministic-demo"
    assert trace.retrieval_mode == "fixture"
    assert trace.estimated_cost_microunits is None
    assert "catalog.search" in {item.tool for item in trace.tools}
    assert trace.last_event_id == len(agent.replay(record.run_id))
    assert goal not in trace.model_dump_json()


def test_identical_evaluation_requests_have_distinct_runs_but_replay_is_stable():
    actor = OpsActor(f"ops-run-identity-{uuid4().hex}", "reviewer")
    request = StartEvaluationRequest(
        dataset_version="v3-final-identity", runner_version="deterministic-2"
    )
    store = PostgresOpsStore(database_url())
    keys = [uuid4().hex for _ in range(12)]
    runs = [store.start_evaluation(actor, request, key) for key in keys]
    assert len({run.run_id for run in runs}) == 12
    recreated = PostgresOpsStore(database_url())
    assert recreated.start_evaluation(actor, request, keys[0]) == runs[0]
    assert {run.run_id for run in runs} <= {run.run_id for run in recreated.evaluations}
    assert len([event for event in recreated.audit if event.actor_ref == actor.ref]) == 12
