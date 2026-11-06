from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

api_installations = Table(
    "api_installations",
    metadata,
    Column("owner_id", UUID(as_uuid=True), primary_key=True),
    Column("token_digest", String(64), nullable=False, unique=True),
)
