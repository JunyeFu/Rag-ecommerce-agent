"""Retrieval-owned PostgreSQL outbox and projection checkpoint metadata."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

outbox_events = Table(
    "retrieval_outbox_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("sequence", Integer, nullable=False, unique=True),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(16), nullable=False),
    Column("payload", JSONB),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error_code", String(64)),
)

projection_checkpoints = Table(
    "retrieval_projection_checkpoints",
    metadata,
    Column("projection_name", String(96), primary_key=True),
    Column("index_version", String(96), nullable=False),
    Column("last_sequence", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("projection_name", "index_version", name="uq_projection_version"),
)
