"""Initial PostgreSQL schema; the SQL snapshot is immutable after release."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(Path(__file__).with_name("0001_schema.sql").read_text())


def downgrade():
    op.execute(
        "DROP TABLE deletion_requests, jobs, usage_events, document_chunks, generations, documents, messages, conversations, users CASCADE"
    )
