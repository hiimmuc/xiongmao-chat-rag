"""Email and password sign-in with JWT access tokens and refresh-token sessions (replaces Cognito)."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE users ADD COLUMN email VARCHAR(254) UNIQUE;
        ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
        CREATE TABLE login_sessions (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_login_sessions_user_id ON login_sessions (user_id);
        """
    )


def downgrade():
    op.execute(
        """
        DROP TABLE login_sessions;
        ALTER TABLE users DROP COLUMN password_hash;
        ALTER TABLE users DROP COLUMN email;
        """
    )
