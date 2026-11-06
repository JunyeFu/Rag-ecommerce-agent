"""Explicit user-data erasure boundary and deterministic in-memory adapter."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ragcommerce_agent_runtime.postgres_connection import connect


class ErasableUserStore(Protocol):
    def delete_user(self, user_id: UUID) -> int: ...


class UserDataEraser(Protocol):
    def erase(self, user_id: UUID) -> int: ...


class InMemoryUserDataEraser:
    """Compose local stores for tests; production must inject one transactional adapter."""

    def __init__(self, *stores: ErasableUserStore) -> None:
        if not stores:
            raise ValueError("at least one user-data store is required")
        self.stores = stores

    def erase(self, user_id: UUID) -> int:
        return sum(store.delete_user(user_id) for store in self.stores)


class PostgresUserDataEraser:
    """Delete owner-scoped durable state; media objects are erased by the media store."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def delete_user(self, user_id: UUID) -> int:
        with connect(self.dsn) as connection:
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM api_turns WHERE owner_id=%s UNION SELECT id FROM agent_runs WHERE conversation_id IN (SELECT thread_id FROM api_threads WHERE owner_id=%s)",
                    (user_id, user_id),
                ).fetchall()
            ]
            threads = connection.execute(
                "SELECT thread_id,mission_id FROM api_threads WHERE owner_id=%s", (user_id,)
            ).fetchall()
            thread_ids = [row[0] for row in threads]
            mission_ids = [row[1] for row in threads]
            list_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT list_id FROM v3_lists WHERE owner_id=%s", (user_id,)
                ).fetchall()
            ]
            count = 0
            count += connection.execute(
                "DELETE FROM v3_demo_quotes WHERE owner_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM v3_tool_receipts WHERE owner_id=%s", (user_id,)
            ).rowcount
            if run_ids:
                count += connection.execute(
                    "DELETE FROM agent_events WHERE run_id=ANY(%s)", (run_ids,)
                ).rowcount
                count += connection.execute(
                    "DELETE FROM agent_checkpoints WHERE run_id=ANY(%s)", (run_ids,)
                ).rowcount
            if run_ids:
                connection.execute("DELETE FROM evidence_refs WHERE run_id=ANY(%s)", (run_ids,))
                connection.execute(
                    "DELETE FROM tool_invocations WHERE step_id IN (SELECT id FROM agent_steps WHERE run_id=ANY(%s))",
                    (run_ids,),
                )
                connection.execute("DELETE FROM agent_steps WHERE run_id=ANY(%s)", (run_ids,))
                connection.execute("DELETE FROM agent_runs WHERE id=ANY(%s)", (run_ids,))
            if list_ids:
                count += connection.execute(
                    "DELETE FROM v3_list_items WHERE list_id=ANY(%s)", (list_ids,)
                ).rowcount
            count += connection.execute(
                "DELETE FROM v3_lists WHERE owner_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM v3_watchers WHERE owner_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM v3_cart_items WHERE owner_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM agent_user_preferences WHERE user_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM api_turns WHERE owner_id=%s", (user_id,)
            ).rowcount
            count += connection.execute(
                "DELETE FROM api_threads WHERE owner_id=%s", (user_id,)
            ).rowcount
            if thread_ids:
                connection.execute("DELETE FROM conversations WHERE id=ANY(%s)", (thread_ids,))
            if mission_ids:
                connection.execute(
                    "DELETE FROM shopping_list_items WHERE list_id IN (SELECT id FROM shopping_lists WHERE mission_id=ANY(%s))",
                    (mission_ids,),
                )
                connection.execute(
                    "DELETE FROM shopping_lists WHERE mission_id=ANY(%s)", (mission_ids,)
                )
                connection.execute("DELETE FROM shopping_missions WHERE id=ANY(%s)", (mission_ids,))
            return count
