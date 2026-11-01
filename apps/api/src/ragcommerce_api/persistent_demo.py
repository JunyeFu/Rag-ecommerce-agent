"""Environment-composed durable V3 local demo application."""

from __future__ import annotations

import gc
import os
from contextlib import asynccontextmanager
from pathlib import Path

from ragcommerce_agent_runtime import (
    PostgresCheckpointStore,
    RuntimeIdentity,
    ShoppingAgent,
    ToolRegistry,
)

from .app import create_app
from .erasure import InMemoryUserDataEraser, PostgresUserDataEraser
from .media import MinioMediaStore
from .media_tools import media_tool_handlers
from .observability import configure_observability
from .postgres_demo import PostgresDemoCommerce
from .postgres_index import PostgresTurnIndex
from .postgres_ops import PostgresOpsStore
from .provider_config import configured_provider
from .retrieval_config import configured_retrieval
from .service import TurnService


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_app():
    root = Path(__file__).resolve().parents[4]
    dsn = required("DATABASE_URL").replace("postgresql+psycopg://", "postgresql://", 1)
    catalog_path = root / "data/demo/catalog.v3.jsonl"
    commerce = PostgresDemoCommerce(
        catalog_path, dsn, real_hybrid=configured_retrieval(catalog_path)
    )
    media = MinioMediaStore(
        dsn,
        required("MINIO_ENDPOINT"),
        required("MINIO_ACCESS_KEY"),
        required("MINIO_SECRET_KEY"),
    )
    checkpoints = PostgresCheckpointStore(dsn)
    index = PostgresTurnIndex(dsn)
    provider = configured_provider()
    agent = ShoppingAgent(
        provider,
        ToolRegistry(media_tool_handlers(commerce.tool_handlers(), media, provider)),
        checkpoints,
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            str(provider.usage().get("model", "deterministic-demo")),
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
            os.environ.get("RETRIEVAL_MODE", "fixture"),
        ),
    )
    service = TurnService(agent, media, index)
    app = create_app(
        service,
        media,
        commerce=commerce,
        ops_store=PostgresOpsStore(dsn),
        data_eraser=InMemoryUserDataEraser(media, PostgresUserDataEraser(dsn)),
        execute_background=False,
    )
    configure_observability(app)
    default_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance):
        async with default_lifespan(instance) as state:
            # The measured startup graph is long-lived; rescanning it pauses
            # Turn acceptance. Runtime objects still use normal cyclic GC.
            gc.collect()
            gc.freeze()
            # Process-lifetime graph; do not unfreeze the interpreter's existing
            # permanent objects when this application's lifespan ends.
            yield state

    app.router.lifespan_context = lifespan
    return app


app = build_app()
