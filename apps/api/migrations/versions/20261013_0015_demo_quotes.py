"""Persist demo quote validity across processes."""

from alembic import op

revision = "20261013_0015"
down_revision = "20261009_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE v3_demo_quotes (owner_id UUID NOT NULL, product_id UUID NOT NULL, quote JSONB NOT NULL, PRIMARY KEY(owner_id,product_id))"
    )


def downgrade() -> None:
    op.drop_table("v3_demo_quotes")
