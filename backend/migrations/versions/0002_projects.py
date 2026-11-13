"""Projects, project-scoped documents/chunks, and per-user preferences."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE projects (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_projects_user_id ON projects (user_id);
        ALTER TABLE users ADD COLUMN preferences JSONB NOT NULL DEFAULT '{}'::jsonb;
        INSERT INTO projects (id, user_id, name) SELECT gen_random_uuid()::text, id, 'My project' FROM users;
        ALTER TABLE conversations ADD COLUMN project_id VARCHAR(36);
        ALTER TABLE documents ADD COLUMN project_id VARCHAR(36);
        ALTER TABLE document_chunks ADD COLUMN project_id VARCHAR(36);
        UPDATE conversations c SET project_id = (SELECT p.id FROM projects p WHERE p.user_id = c.user_id LIMIT 1);
        UPDATE documents d SET project_id = (SELECT p.id FROM projects p WHERE p.user_id = d.user_id LIMIT 1);
        UPDATE document_chunks k SET project_id = d.project_id FROM documents d WHERE d.id = k.document_id;
        ALTER TABLE conversations ALTER COLUMN project_id SET NOT NULL;
        ALTER TABLE documents ALTER COLUMN project_id SET NOT NULL;
        ALTER TABLE document_chunks ALTER COLUMN project_id SET NOT NULL;
        ALTER TABLE conversations ADD FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE documents ADD FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE;
        ALTER TABLE documents ADD CONSTRAINT uq_documents_id_project_id UNIQUE (id, project_id);
        ALTER TABLE document_chunks DROP CONSTRAINT document_chunks_document_id_fkey;
        ALTER TABLE document_chunks ADD CONSTRAINT document_chunks_document_id_project_id_fkey
            FOREIGN KEY (document_id, project_id) REFERENCES documents (id, project_id) ON DELETE CASCADE;
        CREATE INDEX ix_conversations_project_id ON conversations (project_id);
        CREATE INDEX ix_documents_project_id ON documents (project_id);
        CREATE INDEX ix_document_chunks_project_id ON document_chunks (project_id);
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE document_chunks DROP CONSTRAINT document_chunks_document_id_project_id_fkey;
        ALTER TABLE document_chunks ADD FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE;
        ALTER TABLE document_chunks DROP COLUMN project_id;
        ALTER TABLE documents DROP CONSTRAINT uq_documents_id_project_id;
        ALTER TABLE documents DROP COLUMN project_id;
        ALTER TABLE conversations DROP COLUMN project_id;
        ALTER TABLE users DROP COLUMN preferences;
        DROP TABLE projects;
        """
    )
