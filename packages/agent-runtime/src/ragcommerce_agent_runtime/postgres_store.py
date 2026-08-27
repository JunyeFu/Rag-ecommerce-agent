"""PostgreSQL checkpointer plus reproducible, redacted Agent audit records."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from .contracts import (
    AgentEvent,
    EventType,
    RuntimeIdentity,
    ToolEvidence,
    ToolResult,
    TurnCommand,
)
from .store import RunCheckpoint


def plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(item) for item in value]
    return value


def result_json(result: ToolResult) -> dict[str, Any]:
    return {
        "public_data": plain(dict(result.public_data)),
        "evidence": [
            plain({"ref": item.ref, "sha256": item.sha256, "fields": item.fields})
            for item in result.evidence
        ],
        "commercial_fact_fields": sorted(result.commercial_fact_fields),
    }


def step_kind(event_type: EventType) -> str:
    if event_type in {
        EventType.TOOL_STARTED,
        EventType.TOOL_COMPLETED,
        EventType.TOOL_FAILED,
        EventType.APPROVAL_REQUIRED,
    }:
        return "TOOL"
    if event_type is EventType.EVIDENCE:
        return "EVIDENCE"
    if event_type in {EventType.MESSAGE, EventType.COMPLETED}:
        return "RESPONSE"
    return "GUARDRAIL"


class PostgresCheckpointStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def begin_run(
        self, command: TurnCommand, identity: RuntimeIdentity, created_at: datetime
    ) -> None:
        values = (
            command.run_id,
            command.thread_id,
            command.idempotency_key,
            "RUNNING",
            identity.model_version,
            identity.prompt_version,
            identity.policy_version,
            identity.contract_version,
            created_at,
        )
        try:
            with psycopg.connect(self.dsn) as connection:
                connection.execute(
                    """INSERT INTO agent_runs(
                    id,conversation_id,idempotency_key,status,model_version,prompt_version,
                    policy_version,contract_version,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                    values,
                )
                row = connection.execute(
                    """SELECT conversation_id,idempotency_key,model_version,prompt_version,
                    policy_version,contract_version FROM agent_runs WHERE id = %s""",
                    (command.run_id,),
                ).fetchone()
        except UniqueViolation as exc:
            raise ValueError("thread and idempotency key are already bound to another run") from exc
        expected = (
            command.thread_id,
            command.idempotency_key,
            identity.model_version,
            identity.prompt_version,
            identity.policy_version,
            identity.contract_version,
        )
        if row != expected:
            raise ValueError("run identity conflicts with the persisted AgentRun")

    def load(self, run_id: UUID) -> RunCheckpoint | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                "SELECT idempotency_key, checkpoint FROM agent_checkpoints WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            payload = row[1]
            checkpoint = RunCheckpoint(
                run_id,
                row[0],
                started_at=datetime.fromisoformat(payload["started_at"]),
                tool_attempts=int(payload.get("tool_attempts", 0)),
                replans=int(payload.get("replans", 0)),
            )
            for key, value in payload.get("completed_tools", {}).items():
                checkpoint.completed_tools[key] = ToolResult(
                    value["public_data"],
                    tuple(
                        ToolEvidence(item["ref"], item["sha256"], tuple(item["fields"]))
                        for item in value["evidence"]
                    ),
                    frozenset(value["commercial_fact_fields"]),
                )
            rows = connection.execute(
                """SELECT event_id,event_type,data,created_at FROM agent_events
                WHERE run_id = %s ORDER BY event_id""",
                (run_id,),
            ).fetchall()
            checkpoint.events.extend(
                AgentEvent(item[0], EventType(item[1]), run_id, item[2], item[3]) for item in rows
            )
            return checkpoint

    def save(self, checkpoint: RunCheckpoint) -> None:
        payload = {
            "started_at": checkpoint.started_at.isoformat(),
            "tool_attempts": checkpoint.tool_attempts,
            "replans": checkpoint.replans,
            "completed_tools": {
                key: result_json(value) for key, value in checkpoint.completed_tools.items()
            },
        }
        now = datetime.now(UTC)
        with psycopg.connect(self.dsn) as connection:
            cursor = connection.execute(
                """INSERT INTO agent_checkpoints(run_id,idempotency_key,checkpoint,updated_at)
                VALUES (%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET
                checkpoint=EXCLUDED.checkpoint,updated_at=EXCLUDED.updated_at
                WHERE agent_checkpoints.idempotency_key=EXCLUDED.idempotency_key""",
                (checkpoint.run_id, checkpoint.idempotency_key, Jsonb(payload), now),
            )
            if cursor.rowcount != 1:
                raise ValueError("checkpoint idempotency key conflict")
            for event in checkpoint.events:
                connection.execute(
                    """INSERT INTO agent_events(run_id,event_id,event_type,data,created_at)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(run_id,event_id) DO NOTHING""",
                    (
                        checkpoint.run_id,
                        event.id,
                        event.type.value,
                        Jsonb(plain(dict(event.data))),
                        event.created_at,
                    ),
                )
                self._save_audit_event(connection, event)
            connection.execute(
                "UPDATE agent_runs SET status = %s WHERE id = %s",
                (self._run_status(checkpoint.events), checkpoint.run_id),
            )

    @staticmethod
    def _save_audit_event(connection: psycopg.Connection[Any], event: AgentEvent) -> None:
        step_id = uuid5(NAMESPACE_URL, f"urn:rag-commerce:{event.run_id}:event:{event.id}")
        connection.execute(
            """INSERT INTO agent_steps(id,run_id,sequence,kind,created_at)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
            (step_id, event.run_id, event.id - 1, step_kind(event.type), event.created_at),
        )
        invocation = event.data.get("invocation_id")
        if event.type is EventType.TOOL_STARTED and isinstance(invocation, str):
            connection.execute(
                """INSERT INTO tool_invocations(
                id,step_id,tool_name,idempotency_key,status,arguments_sha256,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (
                    UUID(invocation),
                    step_id,
                    str(event.data["tool"]),
                    str(event.data["idempotency_digest"]),
                    "RUNNING",
                    str(event.data["arguments_sha256"]),
                    event.created_at,
                ),
            )
        elif isinstance(invocation, str) and event.type in {
            EventType.TOOL_COMPLETED,
            EventType.TOOL_FAILED,
            EventType.APPROVAL_REQUIRED,
        }:
            status = {
                EventType.TOOL_COMPLETED: "SUCCEEDED",
                EventType.TOOL_FAILED: "FAILED",
                EventType.APPROVAL_REQUIRED: "DENIED",
            }[event.type]
            connection.execute(
                "UPDATE tool_invocations SET status = %s WHERE id = %s",
                (status, UUID(invocation)),
            )
        if event.type is EventType.EVIDENCE:
            evidence_id = uuid5(
                NAMESPACE_URL,
                f"urn:rag-commerce:{event.run_id}:evidence:{event.id}:{event.data['sha256']}",
            )
            connection.execute(
                """INSERT INTO evidence_refs(
                id,run_id,step_id,evidence_type,source_ref,content_sha256,observed_at,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (
                    evidence_id,
                    event.run_id,
                    step_id,
                    "TOOL_RESULT",
                    str(event.data["ref"]),
                    str(event.data["sha256"]),
                    event.created_at,
                    event.created_at,
                ),
            )

    @staticmethod
    def _run_status(events: list[AgentEvent]) -> str:
        types = {event.type for event in events}
        if EventType.COMPLETED in types:
            return "COMPLETED"
        if EventType.FAILED in types:
            return "FAILED"
        if EventType.APPROVAL_REQUIRED in types:
            return "WAITING_APPROVAL"
        return "RUNNING"

    def save_preferences(self, user_id: UUID, values: dict[str, str], consent: bool) -> None:
        if not consent:
            return
        now = datetime.now(UTC)
        with psycopg.connect(self.dsn) as connection:
            for key, value in values.items():
                connection.execute(
                    """INSERT INTO agent_user_preferences(
                    user_id,preference_key,preference_value,consented_at)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(user_id,preference_key) DO UPDATE SET
                    preference_value=EXCLUDED.preference_value,
                    consented_at=EXCLUDED.consented_at""",
                    (user_id, key, value, now),
                )

    def load_preferences(self, user_id: UUID) -> dict[str, str]:
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """SELECT preference_key,preference_value FROM agent_user_preferences
                WHERE user_id = %s ORDER BY preference_key""",
                (user_id,),
            ).fetchall()
            return {row[0]: row[1] for row in rows}

    def delete_user(self, user_id: UUID) -> int:
        with psycopg.connect(self.dsn) as connection:
            cursor = connection.execute(
                "DELETE FROM agent_user_preferences WHERE user_id = %s", (user_id,)
            )
            return cursor.rowcount
