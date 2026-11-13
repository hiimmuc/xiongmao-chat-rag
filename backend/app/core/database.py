"""Database engine, session factory and the declarative base for all tables.

Code outside a request uses `database.Session()` (not `from ... import Session`), so tests can
swap the session factory in this one place.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
Session = sessionmaker(engine, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one session per request."""
    with Session() as db:
        yield db
