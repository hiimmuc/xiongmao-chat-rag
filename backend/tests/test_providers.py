import httpx
import pytest

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
