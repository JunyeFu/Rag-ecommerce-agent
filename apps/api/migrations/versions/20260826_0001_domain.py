"""Create commercial fact and Agent evidence domain schema."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "packages/domain/src"))

from ragcommerce_domain.schema_v1 import metadata  # noqa: E402

revision = "20260826_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), checkfirst=False)
