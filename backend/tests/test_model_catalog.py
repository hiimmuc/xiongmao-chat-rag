import httpx

from app.services import model_catalog


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


OPENAI = {
    "data": [
        {"id": "gpt-4.1"},
        {"id": "gpt-4.1-2025-04-14"},
        {"id": "o4-mini"},
        {"id": "gpt-4o-mini-tts"},
        {"id": "text-embedding-3-small"},
        {"id": "dall-e-3"},
        {"id": "gpt-3.5-turbo"},
    ]
}
GEMINI = {
    "models": [
        {
            "name": "models/gemini-3.6-flash",
            "displayName": "Gemini 3.6 Flash",
            "inputTokenLimit": 1048576,
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-2.0-flash-001", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemma-3-27b-it", "supportedGenerationMethods": ["generateContent"]},
    ]
}


def test_discovery_keeps_only_chat_models(monkeypatch):
    model_catalog._cache.clear()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return FakeResponse(OPENAI if "openai" in url else GEMINI)

    monkeypatch.setattr(model_catalog.httpx, "get", get)
    assert [m["id"] for m in model_catalog.discover("openai", "k")] == ["o4-mini", "gpt-4.1"]
    gemini = model_catalog.discover("gemini", "k")
    assert gemini == [
        dict(
            id="gemini-3.6-flash",
            provider="gemini",
            label="Gemini 3.6 Flash",
            api_model="gemini-3.6-flash",
            context_tokens=1048576,
        )
    ]
    model_catalog.discover("openai", "k")
    assert len(calls) == 2  # second OpenAI lookup came from the cache


def test_discovery_failure_lists_nothing_and_configured_entries_win(monkeypatch):
    from app.core.config import settings

    model_catalog._cache.clear()

    def fail(url, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(model_catalog.httpx, "get", fail)
    assert model_catalog.discover("openai", "k") == []

    cfg = settings()
    monkeypatch.setattr(cfg, "model_discovery", True)
    monkeypatch.setattr(
        cfg,
        "model_catalog_json",
        '[{"id": "fast", "provider": "openai", "label": "Fast", "api_model": "gpt-4.1"}]',
    )
    monkeypatch.setattr(
        model_catalog, "api_key_for", lambda db, user, provider: "k" if provider == "openai" else ""
    )
    monkeypatch.setattr(model_catalog, "discover", lambda provider, key: model_catalog._openai(key))
    monkeypatch.setattr(model_catalog.httpx, "get", lambda url, **kw: FakeResponse(OPENAI))
    assert list(model_catalog.catalog_for(None, "user")) == ["fast", "o4-mini"]
