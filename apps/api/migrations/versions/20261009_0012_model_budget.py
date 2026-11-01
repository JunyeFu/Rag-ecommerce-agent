"""Shared paid-call reservations, without prompts or credentials."""

from alembic import op

revision = "20261009_0012"
down_revision = "20261009_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE model_budget_sessions (session_id VARCHAR(96) PRIMARY KEY, total_limit INTEGER NOT NULL, blocked BOOLEAN NOT NULL)"
    )
    op.execute(
        "CREATE TABLE model_budget_calls (call_id UUID PRIMARY KEY, session_id VARCHAR(96) NOT NULL REFERENCES model_budget_sessions(session_id), run_id UUID NOT NULL, reserved_tokens INTEGER NOT NULL, used_tokens INTEGER, model VARCHAR(120) NOT NULL, status VARCHAR(24) NOT NULL, created_at TIMESTAMPTZ NOT NULL, settled_at TIMESTAMPTZ)"
    )


def downgrade() -> None:
    op.drop_table("model_budget_calls")
    op.drop_table("model_budget_sessions")
