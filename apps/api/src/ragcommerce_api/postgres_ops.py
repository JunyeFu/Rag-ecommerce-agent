"""PostgreSQL-backed governed Ops mutations with restart recovery."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from .ops import (
    AuditEvent,
    EntityConflict,
    EvaluationRun,
    InMemoryOpsStore,
    OpsActor,
    OpsConflict,
    ResolveConflictRequest,
    StartEvaluationRequest,
)


class PostgresOpsStore(InMemoryOpsStore):
    def __init__(self, dsn: str) -> None:
        super().__init__()
        self.dsn = dsn
        self._restore()

    def _restore(self) -> None:
        with psycopg.connect(self.dsn) as connection:
            reservations = connection.execute(
                "SELECT operation,result FROM ops_mutation_reservations ORDER BY created_at"
            ).fetchall()
            audit = connection.execute(
                """SELECT sequence,event_id,actor_ref,action,object_ref,payload_sha256,occurred_at
                FROM ops_audit_events ORDER BY sequence"""
            ).fetchall()
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
            existing = connection.execute(
                """SELECT request_sha256,result FROM ops_mutation_reservations
                WHERE actor_ref=%s AND idempotency_key=%s""",
                (actor.ref, key),
            ).fetchone()
            if existing is not None:
                if existing[0] != digest:
                    raise OpsConflict("Idempotency-Key is bound to a different operation")
                model = EntityConflict if operation == "entity_conflict.resolve" else EvaluationRun
                return model.model_validate(existing[1])
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
                """SELECT request_sha256,result FROM ops_mutation_reservations
                WHERE actor_ref=%s AND idempotency_key=%s""",
                (actor.ref, key),
            ).fetchone()
        if existing is not None:
            if existing[0] != digest:
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
            run_id=f"eval-{digest[:16]}",
            dataset_version=request.dataset_version,
            runner_version=request.runner_version,
            status="QUEUED",
            case_count=0,
            metrics={},
            evidence={
                "local_evidence": "pending:runner",
                "external_gate": "真实模型预算和 held-out 人工双评未批准",
            },
            created_at=datetime.now(UTC),
        )
        value = self._persist(actor, key, digest, "evaluation.start", run.run_id, run)
        assert isinstance(value, EvaluationRun)
        if all(item.run_id != value.run_id for item in self.evaluations):
            self.evaluations.append(value)
        return value


__all__ = ["PostgresOpsStore"]
