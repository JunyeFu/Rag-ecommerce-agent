"""Bound paid acceptance to the authorized 24 first and six corrected scenarios."""

import sqlalchemy as sa
from alembic import op

revision = "20261009_0013"
down_revision = "20261009_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE model_budget_scenarios (session_id VARCHAR(96) NOT NULL REFERENCES model_budget_sessions(session_id), scenario_id VARCHAR(96) NOT NULL, owner_id UUID NOT NULL, scenario_group VARCHAR(16) NOT NULL, phase VARCHAR(16) NOT NULL, root_cause_ref VARCHAR(240), active BOOLEAN NOT NULL, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ, result VARCHAR(24), PRIMARY KEY(session_id,scenario_id))"
    )
    op.add_column("model_budget_calls", sa.Column("scenario_id", sa.String(96)))


def downgrade() -> None:
    op.drop_column("model_budget_calls", "scenario_id")
    op.drop_table("model_budget_scenarios")
