"""Explicit user-data erasure boundary and deterministic in-memory adapter."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


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
