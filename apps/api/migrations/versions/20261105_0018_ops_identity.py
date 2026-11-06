"""Add administrator-provisioned operations identities outside installation ownership."""

from alembic import op
from ragcommerce_api.ops_identity_schema import metadata

revision = "20261105_0018"
down_revision = "20261105_0017"
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=False)
