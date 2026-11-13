"""Helpers shared by the table definitions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.types import UserDefinedType

from app.core.config import settings


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Vector(UserDefinedType):
    """pgvector column sized by EMBEDDING_DIMENSIONS."""

    cache_ok = True

    def get_col_spec(self, **kw):
        return f"vector({settings().embedding_dimensions})"

    def bind_processor(self, dialect):
        return lambda v: "[" + ",".join(str(float(x)) for x in v) + "]" if v is not None else None
