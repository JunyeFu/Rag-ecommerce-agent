"""Persist installation token verifiers, not bearer secrets."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261105_0017"
down_revision = "20261021_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_installations",
        sa.Column("owner_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
    )


def downgrade():
    op.drop_table("api_installations")
