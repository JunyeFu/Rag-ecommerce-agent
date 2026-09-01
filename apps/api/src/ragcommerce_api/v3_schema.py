"""V3 owner-scoped demo list and cart persistence."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

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
