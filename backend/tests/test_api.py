import json
from uuid import uuid4

from sqlalchemy import func, select

from app.models import Document, User

PREFIX = "/api/v1"
ALICE = {"Authorization": "Bearer alice"}
BOB = {"Authorization": "Bearer bob"}


def request(client, method, path, headers=ALICE, **kwargs):
    return client.request(method, PREFIX + path, headers=headers, **kwargs)


def conversation(client, title="New chat"):
    response = request(client, "POST", "/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def document(client, sessions):
    response = request(
        client, "POST", "/documents", files={"file": ("evidence.txt", b"Private evidence", "text/plain")}
    )
    assert response.status_code == 202
    id = response.json()["id"]
    with sessions() as db:
        db.get(Document, id).state = "ready"
        db.commit()
    return id


def test_profile_initialization_and_disabled_account(api):
    client, sessions, _ = api
    assert request(client, "GET", "/me", headers={}).status_code == 401
    first = request(client, "GET", "/me").json()
    assert first["display_name"] == ""
    assert request(client, "GET", "/me").json()["id"] == first["id"]
    assert request(client, "PATCH", "/me", json={"display_name": " Alice "}).json()["display_name"] == "Alice"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        db.get(User, first["id"]).state = "disabled"
        db.commit()
    assert request(client, "GET", "/me").status_code == 403
    with sessions() as db:
        assert db.get(User, first["id"]).state == "disabled"
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_owner_isolation_across_resources(api):
    client, sessions, _ = api
    cid = conversation(client)
    did = document(client, sessions)
    assert request(client, "GET", f"/documents/{did}/download").content == b"Private evidence"
    for path in (
        f"/conversations/{cid}",
        f"/conversations/{cid}/messages",
        f"/documents/{did}",
        f"/documents/{did}/download",
    ):
        assert request(client, "GET", path, headers=BOB).status_code == 404
    for path, body in (
        (f"/conversations/{cid}", {"title": "stolen"}),
        (f"/documents/{did}", {"name": "stolen.txt"}),
    ):
        assert request(client, "PATCH", path, headers=BOB, json=body).status_code == 404
        assert (
            request(
                client, "DELETE", path, headers=dict(BOB, **{"Idempotency-Key": str(uuid4())})
            ).status_code
            == 404
        )
    assert request(client, "GET", "/conversations", headers=BOB).json()["items"] == []
    assert request(client, "GET", "/documents", headers=BOB).json()["items"] == []
    other = request(client, "POST", "/conversations", headers=BOB, json={}).json()["id"]
    assert other != cid
    assert (
        request(
            client, "PATCH", f"/conversations/{other}", headers=BOB, json={"document_ids": [did]}
        ).status_code
        == 404
    )


def test_deletion_idempotency_and_changed_target(api):
    client, _, _ = api
    first, second = conversation(client), conversation(client)
    headers = dict(ALICE, **{"Idempotency-Key": str(uuid4())})
    accepted = request(client, "DELETE", f"/conversations/{first}", headers=headers)
    assert accepted.status_code == 202
    assert request(client, "DELETE", f"/conversations/{first}", headers=headers).json() == accepted.json()
    assert request(client, "DELETE", f"/conversations/{second}", headers=headers).status_code == 409
    assert request(client, "GET", f"/conversations/{first}").status_code == 404
    id = accepted.json()["deletion_id"]
    assert request(client, "GET", f"/deletions/{id}").status_code == 200
    assert request(client, "GET", f"/deletions/{id}", headers=BOB).status_code == 404


def test_account_deletion_requires_password_and_blocks_reprovision(api):
    from app.core.security import hash_password

    client, sessions, _ = api
    cid = conversation(client)
    with sessions() as db:
        db.scalar(select(User).where(User.subject == "alice")).password_hash = hash_password("correct horse")
        db.commit()
    headers = dict(ALICE, **{"Idempotency-Key": str(uuid4())})
    wrong = request(client, "DELETE", "/me", headers=headers, json={"password": "wrong"})
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "wrong_password"
    assert request(client, "GET", f"/conversations/{cid}").status_code == 200
    accepted = request(client, "DELETE", "/me", headers=headers, json={"password": "correct horse"})
    assert accepted.status_code == 202
    assert request(client, "GET", "/me").status_code == 403
    with sessions() as db:
        user = db.scalar(select(User).where(User.subject == "alice"))
        db.delete(user)
        db.commit()
    # The deletion journal still refuses the subject, even though the user row is gone.
    assert request(client, "GET", "/me").status_code == 403


def test_generation_stream_citations_usage_and_idempotency(api, monkeypatch):
    from app.core.config import settings
    from app.services import chat_stream, generations

    client, sessions, _ = api
    cfg = settings()
    monkeypatch.setattr(cfg, "model_catalog_json", json.dumps([{"id": "test-model", "provider": "openai"}]))
    monkeypatch.setattr(cfg, "provider_retention_verified", True)
    monkeypatch.setattr(generations, "provider_enabled", lambda *args: True)
    # Keep this integration test offline, including tiktoken's first-use vocabulary download.
    monkeypatch.setattr(
        "tiktoken.get_encoding",
        lambda name: type(
            "Encoding",
            (),
            {"encode": lambda self, value, **kw: list(value), "decode": lambda self, value: "".join(value)},
        )(),
    )
    cid = conversation(client)
    did = document(client, sessions)
    source = dict(
        id="1",
        document_id=did,
        version=1,
        name="evidence.txt",
        page=None,
        ordinal=0,
        snippet="Private evidence",
    )
    assert request(client, "PATCH", f"/conversations/{cid}", json={"document_ids": [did]}).status_code == 200

    async def retrieve(question, row):
        return [source]

    calls = []

    async def stream(model, messages, system, api_key):
        calls.append(messages)
        yield "text", "Answer [1]"
        yield "usage", dict(input_tokens=10, output_tokens=3, cached_tokens=0, request_id="fake-provider-id")

    monkeypatch.setattr(chat_stream, "retrieve", retrieve)
    monkeypatch.setattr(chat_stream, "stream_text", stream)
    payload = dict(request_id=str(uuid4()), model_id="test-model", message="Question")
    response = request(client, "POST", f"/conversations/{cid}/generations", json=payload)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert "event: done" in response.text
    gid = events[0]["generation_id"]
    saved = request(client, "GET", f"/generations/{gid}").json()
    assert saved["status"] == "completed"
    assert saved["content"] == "Answer [1]"
    assert request(client, "GET", f"/generations/{gid}/citations/1").json() == source
    for path in (f"/generations/{gid}", f"/generations/{gid}/citations/1"):
        assert request(client, "GET", path, headers=BOB).status_code == 404
    replay = request(client, "POST", f"/conversations/{cid}/generations", json=payload)
    assert replay.json()["generation_id"] == gid
    assert len(calls) == 1
    assert (
        request(
            client, "POST", f"/conversations/{cid}/generations", json=dict(payload, message="changed")
        ).status_code
        == 409
    )
    assert (
        request(
            client, "POST", f"/conversations/{conversation(client)}/generations", json=payload
        ).status_code
        == 409
    )
    messages = request(client, "GET", f"/conversations/{cid}/messages").json()["items"]
    assert [x["role"] for x in messages] == ["user", "assistant"]
    assert messages[1]["citations"] == [source]
    assert messages[1]["usage"] == dict(input_tokens=10, output_tokens=3, total_tokens=13, cost_usd=None)
    assert messages[0]["usage"] is None
    done = next(e for e in events if e.get("status") == "completed")
    assert done["usage"]["total_tokens"] == 13
    summary = request(client, "GET", "/usage/summary").json()
    assert summary["known_total_tokens"] == 13
    assert summary["unpriced_records"] == 1
    assert summary["complete"] is False
    assert request(client, "GET", "/usage/summary", headers=BOB).json()["known_total_tokens"] == 0
    assert len(request(client, "GET", "/usage/requests").json()["items"]) == 1
    assert len(request(client, "GET", "/usage/models").json()["items"]) == 1
    assert (
        sum(day["known_total_tokens"] for day in request(client, "GET", "/usage/daily").json()["items"]) == 13
    )
    assert (
        request(
            client, "DELETE", f"/documents/{did}", headers=dict(ALICE, **{"Idempotency-Key": str(uuid4())})
        ).status_code
        == 202
    )
    assert request(client, "GET", f"/generations/{gid}/citations/1").status_code == 404


def test_models_filter_missing_keys_and_processing_policy(api, monkeypatch):
    from app.core.config import settings

    client, _, _ = api
    cfg = settings()
    monkeypatch.setattr(
        cfg,
        "model_catalog_json",
        json.dumps(
            [
                {"id": "openai-test", "provider": "openai", "label": "OpenAI test"},
                {"id": "gemini-test", "provider": "gemini", "label": "Gemini test"},
            ]
        ),
    )
    monkeypatch.setattr(cfg, "openai_api_key", "synthetic-key-not-a-secret")
    monkeypatch.setattr(cfg, "gemini_api_key", "")
    monkeypatch.setattr(cfg, "provider_retention_verified", True)
    assert request(client, "GET", "/models").json()["items"] == [
        {"id": "openai-test", "provider": "openai", "label": "OpenAI test"}
    ]
    monkeypatch.setattr(cfg, "gemini_api_key", "synthetic-gemini-key")
    assert len(request(client, "GET", "/models").json()["items"]) == 2
    cid = conversation(client)
    assert (
        request(
            client,
            "POST",
            f"/conversations/{cid}/generations",
            json={"request_id": str(uuid4()), "model_id": "unconfigured-model", "message": "Hello"},
        ).status_code
        == 422
    )
    monkeypatch.setattr(cfg, "provider_retention_verified", False)
    assert request(client, "GET", "/models").json()["items"] == []
    assert (
        request(
            client,
            "POST",
            f"/conversations/{cid}/generations",
            json={"request_id": str(uuid4()), "model_id": "openai-test", "message": "Hello"},
        ).status_code
        == 503
    )
