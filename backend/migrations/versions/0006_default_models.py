"""Model picker defaults: an empty saved list used to mean "all models", now it means none."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    # Users who never picked models fall back to the default list.
    op.execute("UPDATE users SET preferences = preferences - 'models' WHERE preferences -> 'models' = '[]'::jsonb")


def downgrade():
    pass
