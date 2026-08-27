from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ragcommerce_agent_runtime.schema_v1 import metadata as agent_metadata
from ragcommerce_api.ops_schema_v1 import metadata as ops_metadata
from ragcommerce_api.schema_v1 import metadata as api_metadata
from ragcommerce_domain.persistence import metadata
from ragcommerce_retrieval.schema_v1 import metadata as retrieval_metadata
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def database_url() -> str:
    value = os.environ.get("DOMAIN_DATABASE_URL")
    if not value:
        pytest.skip("DOMAIN_DATABASE_URL is required for migration integration")
    return value


def test_migrated_tables_match_frozen_metadata() -> None:
    engine = create_engine(database_url())
    try:
        assert set(inspect(engine).get_table_names()) == set(metadata.tables) | set(
            retrieval_metadata.tables
        ) | set(agent_metadata.tables) | set(api_metadata.tables) | set(ops_metadata.tables) | {
            "alembic_version"
        }
    finally:
        engine.dispose()


def test_agent_run_idempotency_is_enforced_by_postgresql() -> None:
    engine = create_engine(database_url())
    now = datetime.now(UTC)
    mission_id, conversation_id = uuid4(), uuid4()
    missions = metadata.tables["shopping_missions"]
    conversations = metadata.tables["conversations"]
    runs = metadata.tables["agent_runs"]
    try:
        with engine.begin() as connection:
            connection.execute(
                missions.insert().values(
                    id=mission_id,
                    user_ref="test-user-domain",
                    goal="fixture",
                    budget_minor=None,
                    currency=None,
                    hard_constraints=[],
                    exclusions=[],
                    consented_preferences=[],
                    created_at=now,
                )
            )
            connection.execute(
                conversations.insert().values(
                    id=conversation_id, mission_id=mission_id, created_at=now
                )
            )
            connection.execute(
                runs.insert().values(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    idempotency_key="test-domain-idempotency",
                    status="PENDING",
                    model_version="fake-1",
                    prompt_version="p1",
                    policy_version="policy1",
                    contract_version="0.1.0",
                    created_at=now,
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                runs.insert().values(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    idempotency_key="test-domain-idempotency",
                    status="PENDING",
                    model_version="fake-1",
                    prompt_version="p1",
                    policy_version="policy1",
                    contract_version="0.1.0",
                    created_at=now,
                )
            )
    finally:
        engine.dispose()
