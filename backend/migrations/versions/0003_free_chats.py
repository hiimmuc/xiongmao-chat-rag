"""Free chats: a hidden per-user project kind and chat-scoped session documents."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE projects ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'project';
        ALTER TABLE documents ADD COLUMN conversation_id VARCHAR(36)
            REFERENCES conversations (id) ON DELETE CASCADE;
        CREATE INDEX ix_documents_conversation_id ON documents (conversation_id);
        """
    )


def downgrade():
    op.execute(
        """
        DROP INDEX ix_documents_conversation_id;
        ALTER TABLE documents DROP COLUMN conversation_id;
        ALTER TABLE projects DROP COLUMN kind;
        """
    )
