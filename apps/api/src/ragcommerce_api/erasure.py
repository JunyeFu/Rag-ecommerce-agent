"""Explicit user-data erasure boundary and deterministic in-memory adapter."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg


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
        with psycopg.connect(self.dsn) as connection:
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM api_turns WHERE owner_id=%s", (user_id,)
                ).fetchall()
            ]
            list_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT list_id FROM v3_lists WHERE owner_id=%s", (user_id,)
                ).fetchall()
            ]
            count = 0
            if run_ids:
                count += connection.execute(
                    "DELETE FROM agent_events WHERE run_id=ANY(%s)", (run_ids,)
                ).rowcount
                count += connection.execute(
                    "DELETE FROM agent_checkpoints WHERE run_id=ANY(%s)", (run_ids,)
                ).rowcount
            if list_ids:
                count += connection.execute(
                    "DELETE FROM v3_list_items WHERE list_id=ANY(%s)", (list_ids,)
                ).rowcount
            count += connection.execute(
                "DELETE FROM v3_lists WHERE owner_id=%s", (user_id,)
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
            return count
