"""Agent checkpoint, public event log, and consented preference metadata."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

agent_checkpoints = Table(
    "agent_checkpoints",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("idempotency_key", String(128), nullable=False),
    Column("checkpoint", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
agent_events = Table(
    "agent_events",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", Integer, primary_key=True),
    Column("event_type", String(40), nullable=False),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
user_preferences = Table(
    "agent_user_preferences",
    metadata,
    Column("user_id", UUID(as_uuid=True), primary_key=True),
    Column("preference_key", String(96), primary_key=True),
    Column("preference_value", String(500), nullable=False),
    Column("consented_at", DateTime(timezone=True), nullable=False),
)
