from types import SimpleNamespace

from sqlalchemy import select

from app.core import storage
from app.models import Chunk, Document, User
from app.services import ingestion, retrieval
from worker import main as worker


def auth(owner="alice"):
    return {"Authorization": "Bearer " + owner}


def test_worker_ingestion_vector_retrieval_and_deletion(api, monkeypatch):
    client, sessions, _ = api

    async def embeddings(texts, *args, **kw):
        return [[1.0] + [0.0] * 1535 for _ in texts]

    monkeypatch.setattr(worker, "embed", embeddings)
    monkeypatch.setattr(retrieval, "embed", embeddings)
    # Parsing is separately process-limited in production; this test pins pipeline state and SQL.
    monkeypatch.setattr(worker, "isolated_parse", ingestion.extract_text)
    h = auth()
    client.get("/api/v1/me", headers=h)
    d = client.post(
        "/api/v1/documents",
        headers=h,
        files={"file": ("policy.txt", b"Annual leave is twenty days.", "text/plain")},
    ).json()
    assert d["state"] == "queued"
    assert worker.run_once()
    assert client.get("/api/v1/documents/" + d["id"], headers=h).json()["state"] == "ready"
    with sessions() as db:
        user = db.scalar(select(User).where(User.subject == "alice"))
        owner = user.id
        assert len(db.scalars(select(Chunk)).all()) == 1
    import asyncio

    conv = client.post("/api/v1/conversations", headers=h, json={}).json()
    sources = asyncio.run(
        retrieval.retrieve(
            "How many leave days?",
            SimpleNamespace(
                document_versions=[{"id": d["id"], "version": 1}],
                user_id=owner,
                conversation_id=conv["id"],
                id=None,
            ),
        )
    )
    assert sources[0]["document_id"] == d["id"]
    assert "twenty" in sources[0]["snippet"]
    receipt = client.delete(
        "/api/v1/documents/" + d["id"],
        headers={**h, "Idempotency-Key": "00000000-0000-0000-0000-000000000010"},
    ).json()
    assert worker.run_once()
    assert (
        client.get("/api/v1/deletions/" + receipt["deletion_id"], headers=h).json()["status"] == "completed"
    )
    with sessions() as db:
        assert db.get(Document, d["id"]) is None
        assert db.scalars(select(Chunk)).all() == []


def test_upload_is_unpublished_until_storage_finishes(api, monkeypatch):
    client, sessions, _ = api
    client.get("/api/v1/me", headers=auth())
    original = storage.put

    def checked_put(key, data, **kw):
        if not kw.get("journal"):
            with sessions() as other:
                assert other.scalars(select(Document)).all() == []
        return original(key, data, **kw)

    monkeypatch.setattr(storage, "put", checked_put)
    response = client.post(
        "/api/v1/documents", headers=auth(), files={"file": ("one.txt", b"evidence", "text/plain")}
    )
    assert response.status_code == 202
