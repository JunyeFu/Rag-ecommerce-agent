from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/domain/src"))
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))
sys.path.insert(0, str(ROOT / "packages/retrieval/src"))
sys.path.insert(0, str(ROOT / "apps/api/src"))

from ragcommerce_agent_runtime.schema_v1 import metadata as agent_metadata  # noqa: E402
from ragcommerce_api.ops_schema_v1 import metadata as ops_metadata  # noqa: E402
from ragcommerce_api.schema_v1 import metadata as api_metadata  # noqa: E402
from ragcommerce_domain.persistence import metadata as domain_metadata  # noqa: E402
from ragcommerce_retrieval.schema_v1 import metadata as retrieval_metadata  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required for migrations")
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = MetaData()
for source_metadata in (
    domain_metadata,
    retrieval_metadata,
    agent_metadata,
    api_metadata,
    ops_metadata,
):
    for table in source_metadata.sorted_tables:
        table.to_metadata(target_metadata)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
