"""Persist disabled demo watcher drafts."""

from __future__ import annotations

from alembic import op

revision = "20260923_0009"
down_revision = "20260923_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS v3_watchers (
        watcher_id UUID PRIMARY KEY,
        owner_id UUID NOT NULL,
        thread_id UUID NOT NULL,
        offer_id UUID NOT NULL,
        kind VARCHAR(24) NOT NULL,
        threshold_minor INTEGER NULL,
        created_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_v3_watcher UNIQUE(owner_id,thread_id,offer_id,kind)
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_v3_watchers_owner_id ON v3_watchers(owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_v3_watchers_thread_id ON v3_watchers(thread_id)")


def downgrade() -> None:
    op.drop_table("v3_watchers")
