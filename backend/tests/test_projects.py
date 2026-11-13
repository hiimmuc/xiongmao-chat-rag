import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Chunk, Document, Project, User
from app.services import ingestion, retrieval
from worker import main as worker

A = {"Authorization": "Bearer alice"}
B = {"Authorization": "Bearer bob"}


def test_projects_are_private_and_deleting_the_last_is_refused(api):
    client, _, _ = api
    first = client.get("/api/v1/projects", headers=A).json()["items"]
    assert [p["name"] for p in first] == ["My project"]
    made = client.post("/api/v1/projects", headers=A, json={"name": "Research"})
    assert made.status_code == 201
    pid = made.json()["id"]
    assert (
        client.patch(f"/api/v1/projects/{pid}", headers=A, json={"name": "Papers"}).json()["name"] == "Papers"
    )
    assert client.patch(f"/api/v1/projects/{pid}", headers=B, json={"name": "x"}).status_code == 404
    assert client.get(f"/api/v1/conversations?project_id={pid}", headers=B).status_code == 404
    assert client.post("/api/v1/conversations", headers=B, json={"project_id": pid}).status_code == 404
    only = client.get("/api/v1/projects", headers=B).json()["items"][0]["id"]
    assert (
        client.delete(f"/api/v1/projects/{only}", headers={**B, "Idempotency-Key": str(uuid4())}).status_code
        == 409
    )


def test_documents_and_chats_do_not_cross_projects(api, monkeypatch):
    client, sessions, _ = api

    async def embeddings(texts, *args, **kw):
        return [[1.0] + [0.0] * 1535 for _ in texts]

    monkeypatch.setattr(worker, "embed", embeddings)
    monkeypatch.setattr(retrieval, "embed", embeddings)
    monkeypatch.setattr(worker, "isolated_parse", ingestion.extract_text)
    p1 = client.get("/api/v1/projects", headers=A).json()["items"][0]["id"]
    p2 = client.post("/api/v1/projects", headers=A, json={"name": "Other"}).json()["id"]
    doc = client.post(
        f"/api/v1/documents?project_id={p1}",
        headers=A,
        files={"file": ("a.txt", b"Alpha secret", "text/plain")},
    ).json()
    assert doc["project_id"] == p1 and worker.run_once()
    assert [d["id"] for d in client.get(f"/api/v1/documents?project_id={p1}", headers=A).json()["items"]] == [
        doc["id"]
    ]
    assert client.get(f"/api/v1/documents?project_id={p2}", headers=A).json()["items"] == []
    chat2 = client.post("/api/v1/conversations", headers=A, json={"project_id": p2}).json()
    # A ready document from another project cannot be attached to this chat.
    attach = client.patch(
        f"/api/v1/conversations/{chat2['id']}", headers=A, json={"document_ids": [doc["id"]]}
    )
    assert attach.status_code == 404
    # Even if forced into a snapshot, vector retrieval stays inside the chat's project.
    forced = SimpleNamespace(
        document_versions=[{"id": doc["id"], "version": 1}],
        user_id=_owner(sessions),
        conversation_id=chat2["id"],
        id=None,
    )
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(retrieval.retrieve("secret", forced))
    with sessions() as db:
        assert db.scalar(select(Chunk.project_id)) == p1


def _owner(sessions):
    with sessions() as db:
        return db.scalar(select(User.id).where(User.subject == "alice"))


def test_deleting_a_project_removes_its_documents_and_chunks(api, monkeypatch):
    client, sessions, _ = api

    async def embeddings(texts, *args, **kw):
        return [[1.0] + [0.0] * 1535 for _ in texts]

    monkeypatch.setattr(worker, "embed", embeddings)
    monkeypatch.setattr(worker, "isolated_parse", ingestion.extract_text)
    keep = client.get("/api/v1/projects", headers=A).json()["items"][0]["id"]
    gone = client.post("/api/v1/projects", headers=A, json={"name": "Temp"}).json()["id"]
    client.post(
        f"/api/v1/documents?project_id={gone}",
        headers=A,
        files={"file": ("t.txt", b"temporary", "text/plain")},
    )
    client.post("/api/v1/conversations", headers=A, json={"project_id": gone})
    assert worker.run_once()
    receipt = client.delete(f"/api/v1/projects/{gone}", headers={**A, "Idempotency-Key": str(uuid4())}).json()
    assert client.get(f"/api/v1/conversations?project_id={gone}", headers=A).status_code == 404
    assert worker.run_once()
    assert (
        client.get(f"/api/v1/deletions/{receipt['deletion_id']}", headers=A).json()["status"] == "completed"
    )
    with sessions() as db:
        assert db.get(Project, gone) is None
        assert db.scalars(select(Chunk)).all() == []
        assert db.scalars(select(Document)).all() == []
        assert db.get(Project, keep) is not None


def test_free_chats_use_only_their_session_documents(api, monkeypatch):
    client, sessions, _ = api

    async def embeddings(texts, *args, **kw):
        return [[1.0] + [0.0] * 1535 for _ in texts]

    monkeypatch.setattr(worker, "embed", embeddings)
    monkeypatch.setattr(retrieval, "embed", embeddings)
    monkeypatch.setattr(worker, "isolated_parse", ingestion.extract_text)
    listing = client.get("/api/v1/projects", headers=A).json()
    free, proj = listing["free_id"], listing["items"][0]["id"]
    assert free not in [p["id"] for p in listing["items"]]  # the free scope is never a project
    assert client.patch(f"/api/v1/projects/{free}", headers=A, json={"name": "x"}).status_code == 404
    one = client.post("/api/v1/conversations", headers=A, json={"project_id": free}).json()["id"]
    two = client.post("/api/v1/conversations", headers=A, json={"project_id": free}).json()["id"]
    bare = client.post(
        f"/api/v1/documents?project_id={free}", headers=A, files={"file": ("a.txt", b"alpha", "text/plain")}
    )
    assert bare.status_code == 422  # a free upload must name its chat
    doc = client.post(
        f"/api/v1/documents?project_id={free}&conversation_id={one}",
        headers=A,
        files={"file": ("a.txt", b"alpha fact", "text/plain")},
    ).json()
    assert doc["conversation_id"] == one and worker.run_once()
    mine = client.get(f"/api/v1/documents?project_id={free}&conversation_id={one}", headers=A).json()["items"]
    assert [d["id"] for d in mine] == [doc["id"]]
    assert (
        client.get(f"/api/v1/documents?project_id={free}&conversation_id={two}", headers=A).json()["items"]
        == []
    )
    # Another free chat cannot attach it; a project chat cannot either.
    assert (
        client.patch(
            f"/api/v1/conversations/{two}", headers=A, json={"document_ids": [doc["id"]]}
        ).status_code
        == 404
    )
    pchat = client.post("/api/v1/conversations", headers=A, json={"project_id": proj}).json()["id"]
    assert (
        client.patch(
            f"/api/v1/conversations/{pchat}", headers=A, json={"document_ids": [doc["id"]]}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/conversations/{one}", headers=A, json={"document_ids": [doc["id"]]}
        ).status_code
        == 200
    )
    # Project uploads reject a chat id, and stay out of the free scope.
    bad = client.post(
        f"/api/v1/documents?project_id={proj}&conversation_id={one}",
        headers=A,
        files={"file": ("b.txt", b"beta", "text/plain")},
    )
    assert bad.status_code == 422
    # Deleting the chat removes its session document.
    receipt = client.delete(
        f"/api/v1/conversations/{one}", headers={**A, "Idempotency-Key": str(uuid4())}
    ).json()
    assert worker.run_once()
    assert (
        client.get(f"/api/v1/deletions/{receipt['deletion_id']}", headers=A).json()["status"] == "completed"
    )
    with sessions() as db:
        assert db.get(Document, doc["id"]) is None


def test_model_shortlist_is_validated_and_saved(api, monkeypatch):
    import json

    from app.core.config import settings

    client, _, _ = api
    monkeypatch.setattr(settings(), "model_catalog_json", json.dumps([{"id": "m1", "provider": "openai"}]))
    assert client.patch("/api/v1/me/preferences", headers=A, json={"models": ["nope"]}).status_code == 422
    assert client.patch("/api/v1/me/preferences", headers=A, json={"models": ["m1"]}).json()["models"] == [
        "m1"
    ]
    assert client.get("/api/v1/me/preferences", headers=A).json()["models"] == ["m1"]
    assert client.patch("/api/v1/me/preferences", headers=A, json={"models": []}).json()["models"] == []


def test_model_picker_defaults(api):
    from app.schemas.account import DEFAULT_MODELS

    client, _, _ = api
    assert client.get("/api/v1/me/preferences", headers=A).json()["models"] == list(DEFAULT_MODELS)
