"""Background worker composition root."""

from __future__ import annotations

from typing import Protocol

from ragcommerce_api.service import TurnRecord, TurnService


class DurableTurnIndex(Protocol):
    def claim_next(self) -> TurnRecord | None: ...


class TurnWorker:
    """Claims one PostgreSQL job with SKIP LOCKED and executes it once."""

    def __init__(self, index: DurableTurnIndex, service: TurnService) -> None:
        self.index = index
        self.service = service

    async def run_once(self) -> bool:
        record = self.index.claim_next()
        if record is None:
            return False
        await self.service.execute_claimed(record)
        return True


def health() -> dict[str, str]:
    """Return a side-effect-free process health marker."""

    return {"status": "ok", "component": "worker"}


__all__ = ["TurnWorker", "health"]
