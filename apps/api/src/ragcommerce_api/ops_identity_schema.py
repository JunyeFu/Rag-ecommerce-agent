from sqlalchemy import Boolean, CheckConstraint, Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()
ops_credentials = Table(
    "ops_credentials",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("actor_id", String(64), nullable=False),
    Column("role", String(16), nullable=False),
    Column("token_digest", String(64), nullable=False, unique=True),
    Column("revoked", Boolean, nullable=False, server_default="false"),
    CheckConstraint("role IN ('viewer','reviewer','admin')", name="ck_ops_credential_role"),
)
