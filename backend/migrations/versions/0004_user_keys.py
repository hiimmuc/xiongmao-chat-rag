"""Per-user provider API keys."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE user_keys (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            provider VARCHAR(20) NOT NULL,
            ciphertext TEXT NOT NULL,
            hint VARCHAR(8) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, provider)
        );
        CREATE INDEX ix_user_keys_user_id ON user_keys (user_id);
        """
    )


def downgrade():
    op.execute("DROP TABLE user_keys")
