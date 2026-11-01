"""Persist per-conversation exploration beside Mission version."""

from alembic import op

revision = "20261009_0011"
down_revision = "20261008_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_threads ADD COLUMN IF NOT EXISTS mode VARCHAR(16) NOT NULL DEFAULT 'PURCHASE'"
    )
    op.execute("ALTER TABLE api_threads ADD COLUMN IF NOT EXISTS exploration JSONB")


def downgrade() -> None:
    op.drop_column("api_threads", "exploration")
    op.drop_column("api_threads", "mode")
