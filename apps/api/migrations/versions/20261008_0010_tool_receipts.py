"""Commit write-tool receipts alongside demo commerce mutations."""

from alembic import op

revision = "20261008_0010"
down_revision = "20260923_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS v3_tool_receipts (
        owner_id UUID NOT NULL,
        invocation_id UUID NOT NULL,
        tool_name VARCHAR(40) NOT NULL,
        arguments JSONB NOT NULL,
        result JSONB NOT NULL,
        PRIMARY KEY(owner_id, invocation_id)
    )""")


def downgrade() -> None:
    op.drop_table("v3_tool_receipts")
