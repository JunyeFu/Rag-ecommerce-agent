"""Durable V3 demo worker process."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ragcommerce_agent_runtime import (
    PostgresCheckpointStore,
    RuntimeIdentity,
    ShoppingAgent,
    ToolRegistry,
)
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.postgres_demo import PostgresDemoCommerce
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.provider_config import configured_provider
from ragcommerce_api.service import TurnService

from . import TurnWorker


async def main() -> None:
    root = Path(__file__).resolve().parents[4]
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    commerce = PostgresDemoCommerce(root / "data/demo/catalog.v3.jsonl", dsn)
    index = PostgresTurnIndex(dsn)
    agent = ShoppingAgent(
        configured_provider(),
        ToolRegistry(commerce.tool_handlers()),
        PostgresCheckpointStore(dsn),
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            "deterministic-demo",
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
        ),
    )
    worker = TurnWorker(index, TurnService(agent, InMemoryMediaStore(), index))
    while True:
        if not await worker.run_once():
            await asyncio.sleep(0.25)


if __name__ == "__main__":
    asyncio.run(main())
