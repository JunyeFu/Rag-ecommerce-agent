"""Create retrieval outbox and projection checkpoints."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260826_0002"
down_revision = "20260826_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retrieval_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence", sa.Integer(), nullable=False, unique=True),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64), nullable=True),
    )
    op.create_table(
        "retrieval_projection_checkpoints",
        sa.Column("projection_name", sa.String(96), primary_key=True),
        sa.Column("index_version", sa.String(96), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("projection_name", "index_version", name="uq_projection_version"),
    )


def downgrade() -> None:
    op.drop_table("retrieval_projection_checkpoints")
    op.drop_table("retrieval_outbox_events")
