"""Persist explicit task organization and recommendation feedback, not an implicit profile."""

from alembic import op

revision = "20261021_0016"
down_revision = "20261013_0015"
branch_labels = None
depends_on = None


def upgrade():
    # The initial migration creates current metadata on a fresh database.
    op.execute(
        "ALTER TABLE api_threads ADD COLUMN IF NOT EXISTS experience JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade():
    op.drop_column("api_threads", "experience")
