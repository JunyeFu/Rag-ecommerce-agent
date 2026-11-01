"""PostgreSQL-backed governed Ops mutations with restart recovery."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from ragcommerce_agent_runtime.postgres_connection import connect

from .ops import (
    AgentTraceSummary,
    AuditEvent,
    ConnectorStatus,
    EntityConflict,
    EvaluationRun,
    InMemoryOpsStore,
    OpsActor,
    OpsConflict,
    ReleaseGate,
    ResolveConflictRequest,
    StartEvaluationRequest,
    ToolInvocationSummary,
)


class PostgresOpsStore(InMemoryOpsStore):
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._restore()

    def list_connectors(self) -> list[ConnectorStatus]:
        self._restore()
        return self.connectors

    def list_conflicts(self) -> list[EntityConflict]:
        self._restore()
        return list(self.conflicts.values())

    def list_evaluations(self) -> list[EvaluationRun]:
        self._restore()
        return self.evaluations

    def list_release_gates(self) -> list[ReleaseGate]:
        self._restore()
        return self.release_gates

    def list_audit(self) -> list[AuditEvent]:
        self._restore()
        return self.audit

    def list_traces(self) -> list[AgentTraceSummary]:
        with connect(self.dsn) as connection:
            runs = connection.execute(
                "SELECT r.id,r.status,r.prompt_version,r.model_version,r.created_at FROM agent_runs r "
                "WHERE EXISTS (SELECT 1 FROM agent_events e WHERE e.run_id=r.id "
                "AND e.event_type='run_started' AND e.data->>'agent_version'='shopping-agent-v3-demo') "
                "ORDER BY r.created_at DESC"
            ).fetchall()
            events = connection.execute(
                "SELECT run_id,event_id,event_type,data,created_at FROM agent_events "
                "WHERE run_id=ANY(%s::uuid[]) ORDER BY run_id,event_id",
                ([row[0] for row in runs],),
            ).fetchall()
        by_run = {row[0]: [] for row in runs}
        for event in events:
            by_run[event[0]].append(event)
        traces = []
        for run_id, status, prompt, model, created in runs:
            recorded = by_run[run_id]
            started = {}
            tools = []
            usage = {}
            retrieval_mode = "not_recorded"
            hits = 0
            for _, _, kind, data, occurred in recorded:
                if kind == "run_started":
                    retrieval_mode = data.get("retrieval_mode", "not_recorded")
                elif kind == "tool_started":
                    started[data["invocation_id"]] = (data, occurred)
                elif kind in {"tool_completed", "tool_failed", "approval_required"}:
                    origin, began = started[data["invocation_id"]]
                    tools.append(
                        ToolInvocationSummary(
                            tool=data["tool"],
                            status={
                                "tool_completed": "COMPLETED",
                                "tool_failed": "FAILED",
                                "approval_required": "APPROVAL_REQUIRED",
                            }[kind],
                            arguments_sha256=origin["arguments_sha256"],
                            evidence_refs=[],
                            duration_ms=round(
                                data.get(
                                    "duration_ms",
                                    max(0, round((occurred - began).total_seconds() * 1000)),
                                )
                            ),
                        )
                    )
                elif kind == "evidence" and tools:
                    tools[-1].evidence_refs.append(data["ref"])
                elif kind == "products":
                    hits = len(data["products"])
                if "usage" in data:
                    usage = data["usage"]
            last_at = recorded[-1][4] if recorded else created
            traces.append(
                AgentTraceSummary(
                    run_id=str(run_id),
                    status=status,
                    prompt_version=prompt,
                    model_version=model,
                    retrieval_mode=retrieval_mode,
                    duration_ms=max(0, round((last_at - created).total_seconds() * 1000)),
                    estimated_cost_microunits=None,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    retrieval_hits=hits,
                    last_event_id=recorded[-1][1] if recorded else 0,
                    recovered=any(event[2] == "run_resumed" for event in recorded),
                    tools=tools,
                    redaction_policy="Database events; no raw queries, media or chain of thought. Unknown cost/usage stays null.",
                    created_at=created,
                )
            )
        return traces

    def _restore(self) -> None:
        with psycopg.connect(self.dsn) as connection:
            declared = connection.execute(
                "SELECT kind,payload FROM ops_state_records ORDER BY kind,record_id"
            ).fetchall()
            reservations = connection.execute(
                "SELECT operation,result FROM ops_mutation_reservations ORDER BY created_at"
            ).fetchall()
            audit = connection.execute(
                """SELECT sequence,event_id,actor_ref,action,object_ref,payload_sha256,occurred_at
                FROM ops_audit_events ORDER BY sequence"""
            ).fetchall()
        self.connectors = [
            ConnectorStatus.model_validate(value) for kind, value in declared if kind == "connector"
        ]
        self.conflicts = {
            value["conflict_id"]: EntityConflict.model_validate(value)
            for kind, value in declared
            if kind == "conflict"
        }
        self.release_gates = [
            ReleaseGate.model_validate(value) for kind, value in declared if kind == "gate"
        ]
        self.evaluations = []
        for operation, result in reservations:
            if operation == "entity_conflict.resolve":
                value = EntityConflict.model_validate(result)
                self.conflicts[value.conflict_id] = value
            elif operation == "evaluation.start":
                value = EvaluationRun.model_validate(result)
                if all(item.run_id != value.run_id for item in self.evaluations):
                    self.evaluations.append(value)
        self.audit = [
            AuditEvent.model_validate(dict(zip(AuditEvent.model_fields, row, strict=True)))
            for row in audit
        ]

    def _persist(
        self,
        actor: OpsActor,
        key: str,
        digest: str,
        operation: str,
        object_ref: str,
        result: EntityConflict | EvaluationRun,
    ) -> EntityConflict | EvaluationRun:
        now = datetime.now(UTC)
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"ops:{actor.ref}:{key}",)
            )
            existing = connection.execute(
                """SELECT request_sha256,result,operation,object_ref FROM ops_mutation_reservations
                WHERE actor_ref=%s AND idempotency_key=%s""",
                (actor.ref, key),
            ).fetchone()
            if existing is not None:
                if (
                    existing[0] != digest
                    or existing[2] != operation
                    or (operation == "entity_conflict.resolve" and existing[3] != object_ref)
                ):
                    raise OpsConflict("Idempotency-Key is bound to a different operation")
                model = EntityConflict if operation == "entity_conflict.resolve" else EvaluationRun
                return model.model_validate(existing[1])
            if operation == "entity_conflict.resolve":
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"ops-conflict:{object_ref}",),
                )
                stored = connection.execute(
                    "SELECT payload FROM ops_state_records WHERE kind='conflict' AND record_id=%s FOR UPDATE",
                    (object_ref,),
                ).fetchone()
                if stored and stored[0]["status"] != "PENDING":
                    raise OpsConflict("conflict is already resolved")
                connection.execute(
                    "INSERT INTO ops_state_records(kind,record_id,payload) VALUES ('conflict',%s,%s) ON CONFLICT(kind,record_id) DO UPDATE SET payload=EXCLUDED.payload",
                    (object_ref, Jsonb(result.model_dump(mode="json"))),
                )
            connection.execute(
                """INSERT INTO ops_mutation_reservations(
                actor_ref,idempotency_key,request_sha256,operation,object_ref,result,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    actor.ref,
                    key,
                    digest,
                    operation,
                    object_ref,
                    Jsonb(result.model_dump(mode="json")),
                    now,
                ),
            )
            event_key = f"{actor.ref}:{key}:{operation}:{object_ref}"
            event_id = f"evt-{hashlib.sha256(event_key.encode()).hexdigest()[:60]}"
            connection.execute(
                """INSERT INTO ops_audit_events(
                event_id,actor_ref,action,object_ref,payload_sha256,occurred_at)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (event_id, actor.ref, operation, object_ref, digest, now),
            )
        self._restore()
        return result

    def resolve_conflict(
        self, actor: OpsActor, conflict_id: str, request: ResolveConflictRequest, key: str
    ) -> EntityConflict:
        digest = self._fingerprint(request)
        with psycopg.connect(self.dsn) as connection:
            existing = connection.execute(
                """SELECT request_sha256,result,operation,object_ref FROM ops_mutation_reservations
                WHERE actor_ref=%s AND idempotency_key=%s""",
                (actor.ref, key),
            ).fetchone()
        if existing is not None:
            if (
                existing[0] != digest
                or existing[2] != "entity_conflict.resolve"
                or existing[3] != conflict_id
            ):
                raise OpsConflict("Idempotency-Key is bound to a different operation")
            return EntityConflict.model_validate(existing[1])
        current = self.conflicts.get(conflict_id)
        if current is None:
            raise KeyError(conflict_id)
        if current.status != "PENDING":
            raise OpsConflict("conflict is already resolved")
        resolved = current.model_copy(
            update={"status": "MERGED" if request.decision == "MERGE" else "KEPT_SEPARATE"}
        )
        value = self._persist(actor, key, digest, "entity_conflict.resolve", conflict_id, resolved)
        assert isinstance(value, EntityConflict)
        self.conflicts[conflict_id] = value
        return value

    def start_evaluation(
        self, actor: OpsActor, request: StartEvaluationRequest, key: str
    ) -> EvaluationRun:
        digest = self._fingerprint(request)
        run = EvaluationRun(
            run_id=f"eval-{uuid4().hex}",
            dataset_version=request.dataset_version,
            runner_version=request.runner_version,
            status="QUEUED",
            case_count=0,
            metrics={},
            evidence={
                "local_evidence": "pending:runner",
                "external_gate": "真实模型 competition-v2 challenge 尚未执行",
            },
            created_at=datetime.now(UTC),
        )
        value = self._persist(actor, key, digest, "evaluation.start", run.run_id, run)
        assert isinstance(value, EvaluationRun)
        if all(item.run_id != value.run_id for item in self.evaluations):
            self.evaluations.append(value)
        return value


__all__ = ["PostgresOpsStore"]
