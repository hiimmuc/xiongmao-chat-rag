import httpx
import pytest

from app.core import database
from app.core.config import settings
from app.services import providers


@pytest.mark.parametrize(
    "provider,data",
    [
        ("openai", 'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'),
        ("gemini", 'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}\n\n'),
    ],
)
async def test_truncated_stream_is_not_success(monkeypatch, provider, data):
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=data))
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))
    monkeypatch.setattr(settings(), "provider_retention_verified", True)
    with pytest.raises(providers.ProviderError):
        async for _ in providers.stream_text(
            {"id": "test-model", "provider": provider},
            [{"role": "user", "content": "Hi"}],
            "system",
            "test-key",
        ):
            pass


@pytest.mark.parametrize(
    "provider,data",
    [
        (
            "openai",
            'data: {"type":"response.output_text.delta","delta":"ok"}\n\ndata: {"type":"response.completed","response":{"id":"r","usage":{"input_tokens":3,"output_tokens":1}}}\n\n',
        ),
        (
            "gemini",
            'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":1}}\n\n',
        ),
    ],
)
async def test_complete_provider_stream(monkeypatch, provider, data):
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=data))
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))
    monkeypatch.setattr(settings(), "provider_retention_verified", True)
    events = [
        x
        async for x in providers.stream_text(
            {"id": "test", "provider": provider},
            [{"role": "user", "content": "Hi"}],
            "system",
            "test-key",
        )
    ]
    assert events[0] == ("text", "ok")
    assert events[-1][1]["input_tokens"] == 3


async def test_gemini_embeddings(monkeypatch):
    seen = {}

    def reply(request):
        seen["url"], seen["body"] = str(request.url), request.read().decode()
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 4}, {"values": [0.2] * 4}]})

    client = httpx.AsyncClient
    transport = httpx.MockTransport(reply)
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))
    cfg = settings()
    for name, value in dict(
        provider_retention_verified=True,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        embedding_dimensions=4,
    ).items():
        monkeypatch.setattr(cfg, name, value)
    finalized = {}

    class NoDb:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(database, "Session", NoDb)
    monkeypatch.setattr(providers, "api_key_for", lambda db, user, provider: provider + "-key")
    monkeypatch.setattr(providers.usage, "intent", lambda *a, **kw: "usage-id")
    monkeypatch.setattr(providers.usage, "dispatch", lambda id: None)
    monkeypatch.setattr(providers.usage, "finalize", lambda id, counts=None, **kw: finalized.update(counts))
    vectors = await providers.embed(["a", "b"], "user", "query_embedding")
    assert vectors == [[0.1] * 4, [0.2] * 4]
    assert "gemini-embedding-001:batchEmbedContents" in seen["url"]
    assert "RETRIEVAL_QUERY" in seen["body"] and '"outputDimensionality":4' in seen["body"]
    assert finalized["input_tokens"] is None  # unknown, never zero


def test_system_prompt_names_model_and_forbids_tool_calls():
    from app.services.prompts import build_system

    system = build_system(None, [], False, {"id": "g", "label": "Gemini 3 Flash", "api_model": "gemini-3-flash"})
    assert "Gemini 3 Flash (model `gemini-3-flash`)" in system
    assert "never write tool-call" in system
