"""Persist the current Shopping Mission version."""

from __future__ import annotations

from alembic import op

revision = "20260923_0008"
down_revision = "20260831_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_threads ADD COLUMN IF NOT EXISTS mission_version BIGINT NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE api_threads ADD COLUMN IF NOT EXISTS "
        "selected_product_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE api_threads DROP COLUMN IF EXISTS selected_product_ids")
    op.execute("ALTER TABLE api_threads DROP COLUMN IF EXISTS mission_version")
