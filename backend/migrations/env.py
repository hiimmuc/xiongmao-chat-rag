from alembic import context

import app.models  # noqa: F401  registers every table on Base.metadata
from app.core.database import Base, engine
from app.models.common import Vector

with engine.connect() as connection:
    # Teach reflection the pgvector type, so `alembic check` compares the embedding column cleanly.
    connection.dialect.ischema_names["vector"] = lambda *size: Vector()
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
