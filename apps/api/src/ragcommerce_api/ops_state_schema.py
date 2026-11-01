"""Additive current Ops records, separate from historical create_all metadata."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
ops_state_records = Table(
    "ops_state_records",
    metadata,
    Column("kind", String(32), primary_key=True),
    Column("record_id", String(160), primary_key=True),
    Column("payload", JSONB, nullable=False),
)
