"""Add a recoverable lease timestamp to durable turn claims."""

from __future__ import annotations

from alembic import op

revision = "20260831_0007"
down_revision = "20260830_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_turns ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE api_turns DROP COLUMN IF EXISTS claimed_at")
