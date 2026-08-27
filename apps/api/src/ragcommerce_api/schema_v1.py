"""API ownership, idempotency and media lifecycle metadata."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

api_threads = Table(
    "api_threads",
    metadata,
    Column("thread_id", UUID(as_uuid=True), primary_key=True),
    Column("mission_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("goal", String(500), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

api_turns = Table(
    "api_turns",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("thread_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("command", JSONB, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("owner_id", "thread_id", "idempotency_key", name="uq_api_turn_idempotency"),
)

api_media_objects = Table(
    "api_media_objects",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("content_type", String(100), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("object_key", String(200), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("deleted", Boolean, nullable=False, default=False),
)
