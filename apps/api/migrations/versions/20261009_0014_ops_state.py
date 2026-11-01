"""Persist declared demo connector/conflict/gate state instead of inherited fixtures."""

from alembic import op

revision = "20261009_0014"
down_revision = "20261009_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE ops_state_records (kind VARCHAR(32) NOT NULL, record_id VARCHAR(160) NOT NULL, payload JSONB NOT NULL, PRIMARY KEY(kind,record_id))"
    )


def downgrade() -> None:
    op.drop_table("ops_state_records")
