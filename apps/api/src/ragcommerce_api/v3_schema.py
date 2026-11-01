"""V3 owner-scoped demo list and cart persistence."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()


v3_tool_receipts = Table(
    "v3_tool_receipts",
    metadata,
    Column("owner_id", UUID(as_uuid=True), primary_key=True),
    Column("invocation_id", UUID(as_uuid=True), primary_key=True),
    Column("tool_name", String(40), nullable=False),
    Column("arguments", JSONB, nullable=False),
    Column("result", JSONB, nullable=False),
)

v3_lists = Table(
    "v3_lists",
    metadata,
    Column("list_id", UUID(as_uuid=True), primary_key=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("name", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

v3_list_items = Table(
    "v3_list_items",
    metadata,
    Column("list_id", UUID(as_uuid=True), primary_key=True),
    Column("variant_id", UUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

v3_cart_items = Table(
    "v3_cart_items",
    metadata,
    Column("owner_id", UUID(as_uuid=True), primary_key=True),
    Column("offer_id", UUID(as_uuid=True), primary_key=True),
    Column("quantity", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

v3_watchers = Table(
    "v3_watchers",
    metadata,
    Column("watcher_id", UUID(as_uuid=True), primary_key=True),
    Column("owner_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("thread_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("offer_id", UUID(as_uuid=True), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("threshold_minor", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("owner_id", "thread_id", "offer_id", "kind", name="uq_v3_watcher"),
)
