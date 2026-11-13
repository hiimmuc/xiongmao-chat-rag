from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from app.core import storage
from app.models import Chunk, Document, Generation, User
from app.services import ingestion, retrieval
from worker import main as worker


def auth(owner="alice"):
    return {"Authorization": "Bearer " + owner}


def test_pdf_rejects_scans_and_passwords():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    data = BytesIO()
    writer.write(data)
    with pytest.raises(ValueError, match="Scanned"):
        ingestion.extract_text("scan.pdf", data.getvalue())
    writer.encrypt("secret")
    data = BytesIO()
    writer.write(data)
    with pytest.raises(ValueError, match="Password"):
        ingestion.extract_text("private.pdf", data.getvalue())


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


def test_document_delete_clears_saved_source_snippets(api):
    from uuid import uuid4

    from app.models import Message

    client, sessions, _ = api
    h = auth()
    user = client.get("/api/v1/me", headers=h).json()
    c = client.post("/api/v1/conversations", headers=h, json={}).json()
    d = client.post(
        "/api/v1/documents", headers=h, files={"file": ("private.txt", b"private evidence", "text/plain")}
    ).json()
    with sessions() as db:
        u = Message(conversation_id=c["id"], sequence=1, role="user", content="Question")
        a = Message(conversation_id=c["id"], sequence=2, role="assistant", content="Prior answer")
        db.add_all([u, a])
        db.flush()
        g = Generation(
            user_id=user["id"],
            conversation_id=c["id"],
            user_message_id=u.id,
            assistant_message_id=a.id,
            request_id=str(uuid4()),
            payload_hash="hash",
            model_id="test",
            provider="openai",
            status="completed",
            sources=[dict(id="1", document_id=d["id"], name="private.txt", snippet="private evidence")],
        )
        db.add(g)
        db.commit()
    client.delete("/api/v1/documents/" + d["id"], headers={**h, "Idempotency-Key": str(uuid4())})
    history = client.get("/api/v1/conversations/" + c["id"] + "/messages", headers=h).json()
    assert history["items"][-1]["citations"] == [
        {"id": "1", "document_id": d["id"], "name": "Source deleted", "deleted": True}
    ]
