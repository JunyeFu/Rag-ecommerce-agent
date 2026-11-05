"""PostgreSQL API ownership and idempotency index used across process restarts."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from ragcommerce_agent_runtime import MediaRef, TurnCommand
from ragcommerce_agent_runtime.postgres_connection import bind_connection, connect

from .service import DecisionConflict, ThreadRecord, TurnRecord


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
        "mission_version": command.mission_version,
        "exploration_result": command.exploration_result,
        "media_confirmation": command.media_confirmation,
        "approved_invocations": None
        if command.approved_invocations is None
        else sorted(command.approved_invocations),
        "mission_goal": command.mission_goal,
        "excluded_product_ids": list(command.excluded_product_ids),
        "excluded_categories": list(command.excluded_categories),
        "submitted_text": command.submitted_text,
        "recommendation_feedback": dict(command.recommendation_feedback),
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
        int(value["mission_version"]),
        value.get("exploration_result"),
        value.get("media_confirmation", False),
        None
        if value.get("approved_invocations") is None
        else frozenset(value["approved_invocations"]),
        value.get("mission_goal"),
        tuple(value.get("excluded_product_ids", ())),
        tuple(value.get("excluded_categories", ())),
        value.get("submitted_text"),
        value.get("recommendation_feedback", {}),
    )


class PostgresTurnIndex:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def owner_guard(self, owner_id, blocking=True):
        with connect(self.dsn) as connection:
            if blocking:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"owner:{owner_id}",)
                )
            elif not connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (f"owner:{owner_id}",)
            ).fetchone()[0]:
                raise DecisionConflict("user data operation in progress")
            with bind_connection(self.dsn, connection):
                yield connection

    @contextmanager
    def execution_guard(self, run_id):
        # Separate lock connection: checkpoint commits remain visible during execution.
        with connect(self.dsn) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"execution:{run_id}",),
            ).fetchone()[0]
            if not acquired:
                raise DecisionConflict("run is already executing")
            yield

    def has_active(self, owner_id):
        with connect(self.dsn) as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM api_turns WHERE owner_id=%s AND status IN ('PENDING','RETRY','RUNNING') LIMIT 1",
                    (owner_id,),
                ).fetchone()
                is not None
            )

    @contextmanager
    def mission_guard(self, thread_id: UUID) -> Iterator[None]:
        with connect(self.dsn) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"mission:{thread_id}",),
            ).fetchone()[0]
            if not acquired:
                raise DecisionConflict("Mission update or approval is already in progress")
            yield

    def create_thread(self, record: ThreadRecord) -> None:
        with self.owner_guard(record.owner_id):
            now = datetime.now(UTC)
            with connect(self.dsn) as connection:
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
                    """INSERT INTO api_threads(
                    thread_id,mission_id,owner_id,goal,mission_version,selected_product_ids,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        record.id,
                        record.mission_id,
                        record.owner_id,
                        record.goal,
                        record.mission_version,
                        Jsonb([str(value) for value in record.selected_product_ids]),
                        now,
                    ),
                )

    def get_thread(self, thread_id: UUID) -> ThreadRecord | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT thread_id,mission_id,owner_id,goal,mission_version,selected_product_ids,mode,exploration,experience
                FROM api_threads
                WHERE thread_id = %s""",
                (thread_id,),
            ).fetchone()
        return (
            ThreadRecord(
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                tuple(UUID(str(value)) for value in row[5]),
                row[6],
                row[7],
                row[8],
            )
            if row is not None
            else None
        )

    def reserve(
        self, record: TurnRecord, transition: Callable | None = None
    ) -> tuple[TurnRecord, bool]:
        with self.owner_guard(record.owner_id):
            with ExitStack() as guards, connect(self.dsn) as connection:
                if transition is not None:
                    guards.enter_context(self.mission_guard(record.thread_id))
                thread = connection.execute(
                    """SELECT mission_id,goal,mission_version,mode,exploration,selected_product_ids,experience FROM api_threads
                    WHERE owner_id=%s AND thread_id=%s FOR UPDATE""",
                    (record.owner_id, record.thread_id),
                ).fetchone()
                if thread is None:
                    raise LookupError("thread not found")
                existing = connection.execute(
                    """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                    FROM api_turns WHERE owner_id=%s AND thread_id=%s AND idempotency_key=%s""",
                    (record.owner_id, record.thread_id, record.idempotency_key),
                ).fetchone()
                if existing is not None:
                    return self._record(existing), False
                self._require_no_approved_job(connection, record.owner_id, record.thread_id)
                if transition is None and thread[3] == "DISCOVERY":
                    raise ValueError(
                        "Select a direction or start a new shopping task before sending text"
                    )
                previous = connection.execute(
                    """SELECT status,command FROM api_turns WHERE owner_id=%s AND thread_id=%s
                    ORDER BY created_at DESC LIMIT 1""",
                    (record.owner_id, record.thread_id),
                ).fetchone()
                version = thread[2]
                goal = thread[1]
                if transition is not None:
                    from .exploration import result_for

                    updated = transition(
                        ThreadRecord(
                            record.thread_id,
                            thread[0],
                            record.owner_id,
                            thread[1],
                            thread[2],
                            tuple(UUID(str(value)) for value in thread[5]),
                            thread[3],
                            thread[4],
                            thread[6],
                        )
                    )
                    version = updated.mission_version
                    goal = updated.goal
                    connection.execute(
                        """UPDATE api_threads SET goal=%s,mission_version=%s,mode=%s,exploration=%s,
                        selected_product_ids='[]'::jsonb WHERE thread_id=%s""",
                        (
                            updated.goal,
                            version,
                            updated.mode,
                            Jsonb(updated.exploration),
                            record.thread_id,
                        ),
                    )
                    connection.execute(
                        "UPDATE shopping_missions SET goal=%s WHERE id=%s",
                        (updated.goal, thread[0]),
                    )
                    record.command = replace(
                        record.command,
                        text=updated.goal,
                        exploration_result=None
                        if record.command.media_confirmation
                        else result_for(updated),
                    )
                if (
                    transition is None
                    and previous is not None
                    and previous[0] == "WAITING_CLARIFICATION"
                    and previous[1]["mission_version"] == version
                ):
                    guards.enter_context(self.mission_guard(record.thread_id))
                    goal = f"{thread[1]}; {record.command.text.strip()}"[:500]
                    version += 1
                    connection.execute(
                        """UPDATE api_threads SET goal=%s,mission_version=%s,selected_product_ids='[]'::jsonb
                        WHERE thread_id=%s""",
                        (goal, version, record.thread_id),
                    )
                    connection.execute(
                        "UPDATE shopping_missions SET goal=%s WHERE id=%s", (goal, thread[0])
                    )
                    record.command = replace(record.command, text=goal)
                record.command = replace(
                    record.command,
                    mission_version=version,
                    mission_goal=goal,
                    recommendation_feedback=dict(thread[6].get("feedback", {})),
                    excluded_product_ids=tuple(
                        key.removeprefix("PRODUCT:")
                        for key in thread[6].get("feedback", {})
                        if key.startswith("PRODUCT:")
                    ),
                    excluded_categories=tuple(
                        key.removeprefix("CATEGORY:")
                        for key in thread[6].get("feedback", {})
                        if key.startswith("CATEGORY:")
                    ),
                )
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

    def list_threads(self, owner_id: UUID) -> list[ThreadRecord]:
        with connect(self.dsn) as connection:
            rows = connection.execute(
                "SELECT thread_id,mission_id,owner_id,goal,mission_version,selected_product_ids,mode,exploration,experience FROM api_threads WHERE owner_id=%s ORDER BY created_at DESC,thread_id DESC",
                (owner_id,),
            ).fetchall()
        return [
            ThreadRecord(
                r[0], r[1], r[2], r[3], r[4], tuple(UUID(str(v)) for v in r[5]), r[6], r[7], r[8]
            )
            for r in rows
        ]

    def turns_for_thread(self, owner_id: UUID, thread_id: UUID) -> list[TurnRecord]:
        with connect(self.dsn) as connection:
            rows = connection.execute(
                "SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status FROM api_turns WHERE owner_id=%s AND thread_id=%s ORDER BY created_at,run_id",
                (owner_id, thread_id),
            ).fetchall()
        return [self._record(row) for row in rows]

    def update_experience(self, owner_id: UUID, thread_id: UUID, change: Callable) -> ThreadRecord:
        with self.owner_guard(owner_id):
            from .service import OwnershipError

            with self.mission_guard(thread_id), connect(self.dsn) as connection:
                row = connection.execute(
                    "SELECT thread_id,mission_id,owner_id,goal,mission_version,selected_product_ids,mode,exploration,experience FROM api_threads WHERE owner_id=%s AND thread_id=%s FOR UPDATE",
                    (owner_id, thread_id),
                ).fetchone()
                if row is None:
                    raise OwnershipError("thread not found")
                self._require_no_approved_job(connection, owner_id, thread_id)
                record = ThreadRecord(
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    tuple(UUID(str(v)) for v in row[5]),
                    row[6],
                    row[7],
                    row[8],
                )
                updated = change(record)
                connection.execute(
                    "UPDATE api_threads SET experience=%s,mission_version=%s,selected_product_ids=%s WHERE owner_id=%s AND thread_id=%s",
                    (
                        Jsonb(updated.experience),
                        updated.mission_version,
                        Jsonb([str(v) for v in updated.selected_product_ids]),
                        owner_id,
                        thread_id,
                    ),
                )
                return updated

    def get_run(self, run_id: UUID) -> TurnRecord | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                FROM api_turns WHERE run_id=%s""",
                (run_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def update_status(self, run_id: UUID, value: str) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                "UPDATE api_turns SET status=%s, claimed_at=NULL WHERE run_id=%s",
                (value, run_id),
            )

    def enqueue_approval(self, command: TurnCommand) -> None:
        with self.owner_guard(command.user_id), connect(self.dsn) as connection:
            connection.execute(
                "SELECT thread_id FROM api_threads WHERE owner_id=%s AND thread_id=%s FOR UPDATE",
                (command.user_id, command.thread_id),
            )
            row = connection.execute(
                """UPDATE api_turns SET command=%s,status='PENDING',claimed_at=NULL
                WHERE owner_id=%s AND run_id=%s AND status='WAITING_APPROVAL' RETURNING run_id""",
                (Jsonb(command_json(command)), command.user_id, command.run_id),
            ).fetchone()
            if row is None:
                raise DecisionConflict("approval is no longer pending")

    @staticmethod
    def _require_no_approved_job(connection, owner_id: UUID, thread_id: UUID) -> None:
        active = connection.execute(
            """SELECT 1 FROM api_turns WHERE owner_id=%s AND thread_id=%s
            AND status IN ('PENDING','RETRY','RUNNING')
            AND command->'approved_tools'<>'[]'::jsonb LIMIT 1""",
            (owner_id, thread_id),
        ).fetchone()
        if active:
            raise DecisionConflict("an approved operation is still executing")

    def update_goal(self, owner_id: UUID, thread_id: UUID, goal: str) -> ThreadRecord:
        with self.owner_guard(owner_id):
            with self.mission_guard(thread_id), connect(self.dsn) as connection:
                self._require_no_approved_job(connection, owner_id, thread_id)
                row = connection.execute(
                    """UPDATE api_threads SET goal=%s, mission_version=mission_version+1,
                    selected_product_ids='[]'::jsonb,mode='PURCHASE'
                    WHERE owner_id=%s AND thread_id=%s
                    RETURNING mission_id,mission_version,selected_product_ids""",
                    (goal, owner_id, thread_id),
                ).fetchone()
                if row is None:
                    raise LookupError("thread not found")
                connection.execute(
                    "UPDATE shopping_missions SET goal=%s WHERE id=%s",
                    (goal, row[0]),
                )
            return ThreadRecord(
                thread_id,
                row[0],
                owner_id,
                goal,
                row[1],
                tuple(UUID(str(value)) for value in row[2]),
            )

    def update_comparison(
        self,
        owner_id: UUID,
        thread_id: UUID,
        product_ids: tuple[UUID, ...],
    ) -> ThreadRecord:
        with self.owner_guard(owner_id):
            with connect(self.dsn) as connection:
                row = connection.execute(
                    """UPDATE api_threads SET selected_product_ids=%s
                    WHERE owner_id=%s AND thread_id=%s
                    RETURNING mission_id,goal,mission_version""",
                    (Jsonb([str(value) for value in product_ids]), owner_id, thread_id),
                ).fetchone()
            if row is None:
                raise LookupError("thread not found")
            return ThreadRecord(thread_id, row[0], owner_id, row[1], row[2], product_ids)

    def claim(self, run_id: UUID) -> TurnRecord | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """UPDATE api_turns SET status='RUNNING', claimed_at=NOW() WHERE run_id=%s
                AND status IN ('PENDING','RETRY')
                RETURNING owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status""",
                (run_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def claim_next(self) -> TurnRecord | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """WITH candidate AS (
                    SELECT run_id FROM api_turns
                    WHERE (status IN ('PENDING','RETRY')
                    OR (status='RUNNING' AND claimed_at < NOW() - INTERVAL '5 minutes'))
                    AND pg_try_advisory_xact_lock(hashtextextended('execution:' || run_id::text, 0))
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE api_turns SET status='RUNNING', claimed_at=NOW() FROM candidate
                WHERE api_turns.run_id=candidate.run_id
                RETURNING api_turns.owner_id,api_turns.thread_id,api_turns.run_id,
                api_turns.idempotency_key,api_turns.request_sha256,api_turns.command,api_turns.status"""
            ).fetchone()
        return self._record(row) if row is not None else None

    def latest_for_thread(self, owner_id: UUID, thread_id: UUID) -> TurnRecord | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT owner_id,thread_id,run_id,idempotency_key,request_sha256,command,status
                FROM api_turns WHERE owner_id=%s AND thread_id=%s ORDER BY created_at DESC LIMIT 1""",
                (owner_id, thread_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def delete_user(self, user_id: UUID) -> int:
        with connect(self.dsn) as connection:
            turns = connection.execute(
                "DELETE FROM api_turns WHERE owner_id=%s RETURNING run_id", (user_id,)
            ).fetchall()
            threads = connection.execute(
                "DELETE FROM api_threads WHERE owner_id=%s RETURNING thread_id", (user_id,)
            ).fetchall()
        return len(turns) + len(threads)

    def run_ids_for_mission(
        self, owner_id: UUID, thread_id: UUID, version: int
    ) -> tuple[UUID, ...]:
        with connect(self.dsn) as connection:
            rows = connection.execute(
                "SELECT run_id FROM api_turns WHERE owner_id=%s AND thread_id=%s AND command->>'mission_version'=%s ORDER BY created_at DESC",
                (owner_id, thread_id, str(version)),
            ).fetchall()
        return tuple(row[0] for row in rows)

    @staticmethod
    def _record(row: tuple[Any, ...]) -> TurnRecord:
        return TurnRecord(row[0], row[1], row[2], row[3], row[4], parse_command(row[5]), row[6])
