"""Owner-bound demo quotes shared by API and Worker."""

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
quotes = Table(
    "v3_demo_quotes",
    metadata,
    Column("owner_id", UUID(as_uuid=True), primary_key=True),
    Column("product_id", UUID(as_uuid=True), primary_key=True),
    Column("quote", JSONB, nullable=False),
)
