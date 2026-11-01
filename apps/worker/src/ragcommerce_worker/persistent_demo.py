"""Durable V3 demo worker process."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from threading import Event

from ragcommerce_agent_runtime import (
    PostgresCheckpointStore,
    RuntimeIdentity,
    ShoppingAgent,
    ToolRegistry,
)
from ragcommerce_api.media import MinioMediaStore
from ragcommerce_api.media_tools import media_tool_handlers
from ragcommerce_api.postgres_demo import PostgresDemoCommerce
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.provider_config import configured_provider
from ragcommerce_api.retrieval_config import configured_retrieval
from ragcommerce_api.service import TurnService

from . import TurnWorker


def create_worker() -> TurnWorker:
    root = Path(__file__).resolve().parents[4]
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    catalog_path = root / "data/demo/catalog.v3.jsonl"
    commerce = PostgresDemoCommerce(
        catalog_path, dsn, real_hybrid=configured_retrieval(catalog_path)
    )
    index = PostgresTurnIndex(dsn)
    provider = configured_provider()
    media = MinioMediaStore(
        dsn,
        os.environ["MINIO_ENDPOINT"],
        os.environ["MINIO_ACCESS_KEY"],
        os.environ["MINIO_SECRET_KEY"],
    )
    agent = ShoppingAgent(
        provider,
        ToolRegistry(media_tool_handlers(commerce.tool_handlers(), media, provider)),
        PostgresCheckpointStore(dsn),
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            str(provider.usage().get("model", "deterministic-demo")),
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
            os.environ.get("RETRIEVAL_MODE", "fixture"),
        ),
    )
    return TurnWorker(index, TurnService(agent, media, index))


async def main() -> None:
    stopped = Event()

    def run_lane() -> None:
        # Each lane owns its Agent, model provider and retrieval client; the
        # read-only local BGE session is shared within the process. Synchronous
        # PostgreSQL work cannot block another lane's model or SSE progress.
        async def consume() -> None:
            worker = create_worker()
            while not stopped.is_set():
                if not await worker.run_once():
                    await asyncio.sleep(0.25)

        try:
            asyncio.run(consume())
        finally:
            stopped.set()

    # Bounded concurrency fixes the observed 30-Mission serial queue. Claims
    # still use SKIP LOCKED; a lane failure stops the process, never retries.
    await asyncio.gather(*(asyncio.to_thread(run_lane) for _ in range(8)))


if __name__ == "__main__":
    asyncio.run(main())
