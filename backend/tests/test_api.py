import json
from uuid import uuid4

import pytest
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


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/conversations", {"title": "   "}),
        ("POST", "/conversations", {"title": "ok", "user_id": "injected"}),
        ("GET", "/conversations/not-a-uuid", None),
        ("GET", "/conversations?cursor=invalid", None),
        ("GET", "/documents?limit=101", None),
        ("GET", "/usage/summary?timezone=invalid", None),
        ("GET", "/usage/summary?from=2026-11-08&to=2026-11-07", None),
        ("PATCH", "/me", {"display_name": "  "}),
    ],
)
def test_request_validation(api, method, path, body):
    client, _, _ = api
    response = request(client, method, path, **({"json": body} if body is not None else {}))
    assert response.status_code == 422
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("zone", ["UTC", "Asia/Seoul", "America/Los_Angeles"])
def test_usage_accepts_real_time_zones(api, zone):
    # The browser sends its own IANA zone; the server must know them all (tzdata is a dependency).
    client, _, _ = api
    for route in ("summary", "daily", "models", "requests"):
        response = request(client, "GET", f"/usage/{route}?from=2026-11-01&to=2026-11-12&timezone={zone}")
        assert response.status_code == 200, (route, zone, response.json())


def test_tzdata_is_a_direct_dependency():
    # Slim Linux images have no system zone database; without the package every zone is "invalid".
    from importlib.metadata import requires

    assert any(r.startswith("tzdata") for r in requires("xiongmao-chat"))


def test_cors_preflight(api):
    client, _, _ = api
    for origin, expected in [("http://localhost:5173", 200), ("https://untrusted.example", 400)]:
        response = request(
            client,
            "OPTIONS",
            "/conversations",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type,Idempotency-Key",
            },
        )
        assert response.status_code == expected
        if expected == 200:
            assert response.headers["access-control-allow-origin"] == origin
        else:
            assert "access-control-allow-origin" not in response.headers


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


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "bad", "model_id": "test-model", "message": "hello"},
        {"request_id": str(uuid4()), "model_id": "test-model", "message": "   "},
        {"request_id": str(uuid4()), "model_id": "test-model", "message": "hello", "retry_of": str(uuid4())},
        {"request_id": str(uuid4()), "model_id": "test-model", "message": "hello", "user_id": "injected"},
    ],
)
def test_generation_validation(api, body):
    client, _, _ = api
    cid = conversation(client)
    assert request(client, "POST", f"/conversations/{cid}/generations", json=body).status_code == 422
    assert request(client, "GET", f"/conversations/{cid}/messages").json()["items"] == []


def test_deletion_requires_uuid_key(api):
    client, _, _ = api
    cid = conversation(client)
    assert request(client, "DELETE", f"/conversations/{cid}").status_code == 422
    headers = dict(ALICE, **{"Idempotency-Key": "invalid"})
    assert request(client, "DELETE", f"/conversations/{cid}", headers=headers).status_code == 422
    assert request(client, "GET", f"/conversations/{cid}").status_code == 200


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


def test_switch_model_and_retry_use_current_selection(api, monkeypatch):
    from app.core.config import settings
    from app.models import Generation
    from app.services import chat_stream, generations

    client, sessions, _ = api
    cfg = settings()
    monkeypatch.setattr(
        cfg,
        "model_catalog_json",
        json.dumps(
            [
                {"id": "openai-test", "provider": "openai", "api_model": "openai-api-model"},
                {"id": "gemini-test", "provider": "gemini", "api_model": "gemini-api-model"},
            ]
        ),
    )
    monkeypatch.setattr(cfg, "provider_retention_verified", True)
    monkeypatch.setattr(generations, "provider_enabled", lambda *args: True)
    monkeypatch.setattr(
        "tiktoken.get_encoding",
        lambda _: type(
            "Encoding",
            (),
            {
                "encode": lambda self, value, **kw: list(value),
                "decode": lambda self, value: "".join(value),
            },
        )(),
    )
    cid = conversation(client)
    calls = []

    async def stream(model, messages, system, api_key):
        calls.append((model.copy(), messages))
        if len(calls) == 1:
            yield "text", "Incomplete answer"
            raise chat_stream.ProviderError("Synthetic failed answer")
        yield "text", "Complete answer"
        yield "usage", {"input_tokens": 5, "output_tokens": 2, "cached_tokens": 0}

    monkeypatch.setattr(chat_stream, "stream_text", stream)
    first = request(
        client,
        "POST",
        f"/conversations/{cid}/generations",
        json={"request_id": str(uuid4()), "model_id": "openai-test", "message": "Original question"},
    )
    assert "event: error" in first.text
    events = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]
    failed_id = events[0]["generation_id"]
    retry = request(
        client,
        "POST",
        f"/conversations/{cid}/generations",
        json={"request_id": str(uuid4()), "model_id": "gemini-test", "retry_of": failed_id},
    )
    assert "event: done" in retry.text
    assert [call[0]["provider"] for call in calls] == ["openai", "gemini"]
    assert calls[1][0]["api_model"] == "gemini-api-model"
    assert calls[1][1] == [{"role": "user", "content": "Original question"}]
    with sessions() as db:
        attempts = db.scalars(
            select(Generation).where(Generation.conversation_id == cid).order_by(Generation.created_at)
        ).all()
        assert [(g.model_id, g.provider, g.status) for g in attempts] == [
            ("openai-test", "openai", "failed"),
            ("gemini-test", "gemini", "completed"),
        ]
    next_answer = request(
        client,
        "POST",
        f"/conversations/{cid}/generations",
        json={"request_id": str(uuid4()), "model_id": "openai-test", "message": "Next question"},
    )
    assert "event: done" in next_answer.text
    assert calls[-1][0]["id"] == "openai-test"
    assert [m["content"] for m in calls[-1][1]] == ["Original question", "Complete answer", "Next question"]
    rows = request(client, "GET", "/usage/models").json()["items"]
    assert {row["model_id"] for row in rows} == {"openai-test", "gemini-test"}
