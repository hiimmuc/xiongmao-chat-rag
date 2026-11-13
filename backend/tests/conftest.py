import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def api(monkeypatch, tmp_path):
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("Set DATABASE_URL to run PostgreSQL API integration tests")
    import app.models  # noqa: F401  registers every table
    from app import main
    from app.core import database, security
    from app.core.config import settings
    from app.core.database import Base, get_db
    from app.models import User

    schema = "api_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
    sessions = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine, checkfirst=False)

    def override_db():
        with sessions() as db:
            yield db

    def token_is_subject(token):
        """Test shortcut: the bearer token is the user's subject ("alice", "bob"), created on first use.
        tests/test_auth.py covers the real sign-up, sign-in and JWT checks."""
        with sessions() as db:
            db.execute(insert(User).values(id=str(uuid4()), subject=token).on_conflict_do_nothing())
            db.commit()
        return dict(sub=token)

    monkeypatch.setattr(security, "verify_token", token_is_subject)
    monkeypatch.setattr(database, "Session", sessions)
    cfg = settings()
    monkeypatch.setattr(cfg, "storage_dir", str(tmp_path))
    monkeypatch.setattr(cfg, "app_env", "local")
    monkeypatch.setattr(cfg, "model_discovery", False)  # tests never call the real providers
    main.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(main.app) as client:
            yield client, sessions, None
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
