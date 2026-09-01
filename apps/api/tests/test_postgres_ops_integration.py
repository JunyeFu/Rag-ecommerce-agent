from __future__ import annotations

import os
from datetime import UTC, datetime
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
