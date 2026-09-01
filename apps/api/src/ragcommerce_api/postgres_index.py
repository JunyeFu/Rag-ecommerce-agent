"""PostgreSQL API ownership and idempotency index used across process restarts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from ragcommerce_agent_runtime import MediaRef, TurnCommand

from .service import ThreadRecord, TurnRecord


def command_json(command: TurnCommand) -> dict[str, Any]:
    return {
        "user_id": str(command.user_id),
        "thread_id": str(command.thread_id),
        "run_id": str(command.run_id),
        "idempotency_key": command.idempotency_key,
        "text": command.text,
        "media": [{"id": str(item.id), "kind": item.kind} for item in command.media],
        "approved_tools": sorted(command.approved_tools),
        "allow_reversible_writes": command.allow_reversible_writes,
        "consent_preference_memory": command.consent_preference_memory,
    }


def parse_command(value: dict[str, Any]) -> TurnCommand:
    return TurnCommand(
        UUID(value["user_id"]),
        UUID(value["thread_id"]),
        UUID(value["run_id"]),
        value["idempotency_key"],
        value["text"],
        tuple(MediaRef(UUID(item["id"]), item["kind"]) for item in value["media"]),
        frozenset(value["approved_tools"]),
        bool(value["allow_reversible_writes"]),
        bool(value["consent_preference_memory"]),
    )


class PostgresTurnIndex:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def create_thread(self, record: ThreadRecord) -> None:
        now = datetime.now(UTC)
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """INSERT INTO shopping_missions(
                id,user_ref,goal,budget_minor,currency,hard_constraints,exclusions,
                consented_preferences,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.mission_id,
                    f"api-user:{record.owner_id}",
                    record.goal,
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
                (record.id, record.mission_id, now),
            )
            connection.execute(
                """INSERT INTO api_threads(thread_id,mission_id,owner_id,goal,created_at)
                VALUES (%s,%s,%s,%s,%s)""",
                (record.id, record.mission_id, record.owner_id, record.goal, now),
            )

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT thread_id,mission_id,owner_id,goal FROM api_threads
                WHERE thread_id = %s""",
                (thread_id,),
            ).fetchone()
        return ThreadRecord(*row) if row is not None else None

    def reserve(self, record: TurnRecord) -> tuple[TurnRecord, bool]:
        with psycopg.connect(self.dsn) as connection:
            inserted = connection.execute(
                """INSERT INTO api_turns(
                run_id,owner_id,thread_id,idempotency_key,request_sha256,command,status,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(owner_id,thread_id,idempotency_key) DO NOTHING RETURNING run_id""",
                (
                    record.run_id,
                    record.owner_id,
                    record.thread_id,
                    record.idempotency_key,
                    record.fingerprint,
                    Jsonb(command_json(record.command)),
                    record.execution_status,
                    datetime.now(UTC),
                ),
            ).fetchone()
            if inserted is not None:
                return record, True
            row = connection.execute(
                """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                FROM api_turns WHERE owner_id=%s AND thread_id=%s AND idempotency_key=%s""",
                (record.owner_id, record.thread_id, record.idempotency_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("idempotency reservation disappeared")
        return self._record(row), False

    def get_run(self, run_id: UUID) -> TurnRecord | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                FROM api_turns WHERE run_id=%s""",
                (run_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def update_status(self, run_id: UUID, value: str) -> None:
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE api_turns SET status=%s, claimed_at=NULL WHERE run_id=%s",
                (value, run_id),
            )

    def update_goal(self, owner_id: UUID, thread_id: UUID, goal: str) -> None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """UPDATE api_threads SET goal=%s WHERE owner_id=%s AND thread_id=%s
                RETURNING mission_id""",
                (goal, owner_id, thread_id),
            ).fetchone()
            if row is None:
                raise LookupError("thread not found")
            connection.execute(
                "UPDATE shopping_missions SET goal=%s WHERE id=%s",
                (goal, row[0]),
            )

    def claim(self, run_id: UUID) -> TurnRecord | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """UPDATE api_turns SET status='RUNNING', claimed_at=NOW() WHERE run_id=%s
                AND status IN ('PENDING','RETRY')
                RETURNING owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status""",
                (run_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def claim_next(self) -> TurnRecord | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """WITH candidate AS (
                    SELECT run_id FROM api_turns
                    WHERE status IN ('PENDING','RETRY')
                    OR (status='RUNNING' AND claimed_at < NOW() - INTERVAL '5 minutes')
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE api_turns SET status='RUNNING', claimed_at=NOW() FROM candidate
                WHERE api_turns.run_id=candidate.run_id
                RETURNING api_turns.owner_id,api_turns.thread_id,api_turns.run_id,
                api_turns.idempotency_key,api_turns.request_sha256,api_turns.command,api_turns.status"""
            ).fetchone()
        return self._record(row) if row is not None else None

    def latest_for_thread(self, owner_id: UUID, thread_id: UUID) -> TurnRecord | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                FROM api_turns WHERE owner_id=%s AND thread_id=%s ORDER BY created_at DESC LIMIT 1""",
                (owner_id, thread_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def delete_user(self, user_id: UUID) -> int:
        with psycopg.connect(self.dsn) as connection:
            turns = connection.execute(
                "DELETE FROM api_turns WHERE owner_id=%s RETURNING run_id", (user_id,)
            ).fetchall()
            threads = connection.execute(
                "DELETE FROM api_threads WHERE owner_id=%s RETURNING thread_id", (user_id,)
            ).fetchall()
        return len(turns) + len(threads)

    @staticmethod
    def _record(row: tuple[Any, ...]) -> TurnRecord:
        return TurnRecord(row[0], row[1], row[2], row[3], row[4], parse_command(row[5]), row[6])
