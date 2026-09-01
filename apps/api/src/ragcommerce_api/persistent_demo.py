"""Environment-composed durable V3 local demo application."""

from __future__ import annotations

import os
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
from .observability import configure_observability
from .postgres_demo import PostgresDemoCommerce
from .postgres_index import PostgresTurnIndex
from .postgres_ops import PostgresOpsStore
from .provider_config import configured_provider
from .service import TurnService


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_app():
    root = Path(__file__).resolve().parents[4]
    dsn = required("DATABASE_URL").replace("postgresql+psycopg://", "postgresql://", 1)
    commerce = PostgresDemoCommerce(root / "data/demo/catalog.v3.jsonl", dsn)
    media = MinioMediaStore(
        dsn,
        required("MINIO_ENDPOINT"),
        required("MINIO_ACCESS_KEY"),
        required("MINIO_SECRET_KEY"),
    )
    checkpoints = PostgresCheckpointStore(dsn)
    index = PostgresTurnIndex(dsn)
    agent = ShoppingAgent(
        configured_provider(),
        ToolRegistry(commerce.tool_handlers()),
        checkpoints,
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            "deterministic-demo",
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
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
    return app


app = build_app()
