"""Persistent operations audit and governed mutation records."""

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

ops_audit_events = Table(
    "ops_audit_events",
    metadata,
    Column("sequence", BigInteger, primary_key=True, autoincrement=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("actor_ref", String(80), nullable=False, index=True),
    Column("action", String(100), nullable=False),
    Column("object_ref", String(160), nullable=False, index=True),
    Column("payload_sha256", String(64), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

ops_mutation_reservations = Table(
    "ops_mutation_reservations",
    metadata,
    Column("actor_ref", String(80), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_sha256", String(64), nullable=False),
    Column("operation", String(100), nullable=False),
    Column("object_ref", String(160), nullable=False),
    Column("result", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
