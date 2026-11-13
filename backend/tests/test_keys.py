import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.models import UserKey
from app.services import api_keys

A = {"Authorization": "Bearer alice"}
B = {"Authorization": "Bearer bob"}


@pytest.fixture
def stored(monkeypatch):
    monkeypatch.setattr(settings(), "key_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings(), "openai_api_key", "shared-openai-key")
    monkeypatch.setattr(settings(), "gemini_api_key", "")


def test_status_reports_shared_none_and_own_without_leaking_the_key(api, stored):
    client, sessions, _ = api
    items = {i["provider"]: i for i in client.get("/api/v1/me/keys", headers=A).json()["items"]}
    assert items["openai"]["source"] == "shared" and items["gemini"]["source"] == "none"
    saved = client.put("/api/v1/me/keys/gemini", headers=A, json={"api_key": "AIza-secret-value-1234"})
    assert saved.json() == {"provider": "gemini", "source": "own", "hint": "1234"}
    assert "secret" not in client.get("/api/v1/me/keys", headers=A).text
    with sessions() as db:
        assert "secret" not in db.scalar(select(UserKey.ciphertext))  # stored encrypted
    other = client.get("/api/v1/me/keys", headers=B).json()["items"]
    assert {i["provider"]: i["source"] for i in other}["gemini"] == "none"


def test_own_key_wins_and_removal_restores_the_shared_key(api, stored):
    client, sessions, _ = api
    client.put("/api/v1/me/keys/openai", headers=A, json={"api_key": "sk-own-key-0001"})
    with sessions() as db:
        user = db.scalar(select(UserKey.user_id))
        assert api_keys.api_key_for(db, user, "openai") == "sk-own-key-0001"
    assert client.delete("/api/v1/me/keys/openai", headers=A).json()["source"] == "shared"
    with sessions() as db:
        assert api_keys.api_key_for(db, user, "openai") == "shared-openai-key"


def test_key_storage_needs_configuration_and_valid_input(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(settings(), "key_encryption_key", "")
    assert (
        client.put("/api/v1/me/keys/openai", headers=A, json={"api_key": "sk-valid-key-1"}).status_code == 503
    )
    assert (
        client.put("/api/v1/me/keys/other", headers=A, json={"api_key": "sk-valid-key-1"}).status_code == 422
    )
    assert client.put("/api/v1/me/keys/openai", headers=A, json={"api_key": "short"}).status_code == 422


def test_connection_test_maps_provider_answers(api, stored, monkeypatch):
    client, _, _ = api
    answers = iter([200, 401, 500])
    monkeypatch.setattr(api_keys.httpx, "get", lambda *a, **kw: type("R", (), {"status_code": next(answers)})())
    url = "/api/v1/me/keys/openai/test"
    assert client.post(url, headers=A, json={"api_key": "sk-candidate-key"}).json() == {
        "ok": True,
        "message": "Connected",
    }
    assert client.post(url, headers=A, json={}).json()["message"] == "The provider rejected this key"
    assert "HTTP 500" in client.post(url, headers=A, json={}).json()["message"]
    assert client.post("/api/v1/me/keys/gemini/test", headers=A, json={}).json() == {
        "ok": False,
        "message": "No key is configured",
    }
