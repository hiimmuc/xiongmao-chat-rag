"""OpenAI and Gemini adapters that normalize streamed text, usage and embeddings."""

import json

import httpx

from app.core import database
from app.core.config import settings
from app.services import usage
from app.services.api_keys import api_key_for


class ProviderError(Exception):
    pass


def ensure_paid_enabled():
    if not settings().provider_retention_verified:
        raise ProviderError("Provider processing and retention must be reviewed before use")


async def stream_text(model, messages, system, api_key):
    """Yield `("text", chunk)` and one `("usage", counts)` from the provider stream.

    Raises:
        ProviderError: If the provider fails or the stream ends before completion."""
    cfg = settings()
    ensure_paid_enabled()
    if model["provider"] == "openai":
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": "Bearer " + api_key}
        body = dict(
            model=model.get("api_model", model["id"]),
            input=messages,
            instructions=system,
            stream=True,
            store=False,
            max_output_tokens=cfg.max_output_tokens,
        )
    else:
        api_model = model.get("api_model", model["id"])
        if any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._" for c in api_model
        ):
            raise ProviderError("Invalid configured Gemini model")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{api_model}:streamGenerateContent?alt=sse"
        headers = {"x-goog-api-key": api_key}
        body = dict(
            contents=[
                dict(role="model" if x["role"] == "assistant" else "user", parts=[dict(text=x["content"])])
                for x in messages
            ],
            systemInstruction=dict(parts=[dict(text=system)]),
            generationConfig=dict(maxOutputTokens=cfg.max_output_tokens),
        )
    completed = False
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code != 200:
                raise ProviderError("Provider unavailable; check service configuration or retry later")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    continue
                data = json.loads(value)
                if model["provider"] == "openai":
                    kind = data.get("type")
                    if kind == "response.output_text.delta":
                        yield "text", data["delta"]
                    elif kind == "response.completed":
                        completed = True
                        r = data["response"]
                        u = r.get("usage", {})
                        yield (
                            "usage",
                            dict(
                                input_tokens=u.get("input_tokens"),
                                output_tokens=u.get("output_tokens"),
                                cached_tokens=u.get("input_tokens_details", {}).get("cached_tokens", 0),
                                request_id=r.get("id"),
                            ),
                        )
                    elif kind in ("error", "response.failed", "response.incomplete"):
                        raise ProviderError("Provider did not complete the answer")
                else:
                    for candidate in data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("text") and not part.get("thought"):
                                yield "text", part["text"]
                        if candidate.get("finishReason") == "STOP":
                            completed = True
                        if candidate.get("finishReason") not in (None, "STOP"):
                            raise ProviderError("Provider stopped before completing the answer")
                    u = data.get("usageMetadata")
                    if u:
                        output = u.get("candidatesTokenCount")
                        if output is not None:
                            output += u.get("thoughtsTokenCount", 0)
                        yield (
                            "usage",
                            dict(
                                input_tokens=u.get("promptTokenCount"),
                                output_tokens=output,
                                cached_tokens=u.get("cachedContentTokenCount", 0),
                                request_id=data.get("responseId"),
                            ),
                        )

    if not completed:
        raise ProviderError("Provider stream ended before completion")


async def _openai_embeddings(client, cfg, api_key, texts, operation):
    response = await client.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": "Bearer " + api_key},
        json={"model": cfg.embedding_model, "input": texts, "dimensions": cfg.embedding_dimensions},
    )
    response.raise_for_status()
    data = response.json()
    vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    counts = dict(
        input_tokens=data.get("usage", {}).get("prompt_tokens"),
        output_tokens=0,
        request_id=response.headers.get("x-request-id"),
    )
    return vectors, counts


async def _gemini_embeddings(client, cfg, api_key, texts, operation):
    model = "models/" + cfg.embedding_model
    task = "RETRIEVAL_QUERY" if operation == "query_embedding" else "RETRIEVAL_DOCUMENT"
    response = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/{model}:batchEmbedContents",
        headers={"x-goog-api-key": api_key},
        json=dict(
            requests=[
                dict(
                    model=model,
                    content=dict(parts=[dict(text=t)]),
                    taskType=task,
                    outputDimensionality=cfg.embedding_dimensions,
                )
                for t in texts
            ]
        ),
    )
    response.raise_for_status()
    vectors = [e["values"] for e in response.json()["embeddings"]]
    # Gemini does not report embedding token counts, so usage stays unknown rather than zero.
    return vectors, dict(input_tokens=None, output_tokens=0, request_id=None)


EMBEDDERS = {"openai": _openai_embeddings, "gemini": _gemini_embeddings}


async def embed(texts, user_id, operation, **refs):
    """Embed `texts` with the shared embedding model, recording usage under `operation`.

    EMBEDDING_PROVIDER picks OpenAI or Gemini; every document and query must use the same one.

    Raises:
        ProviderError: If no key is available or the request fails."""
    cfg = settings()
    ensure_paid_enabled()
    provider = cfg.embedding_provider
    if provider not in EMBEDDERS:
        raise ProviderError("Embedding provider is not configured")
    with database.Session() as db:
        api_key = api_key_for(db, user_id, provider)
    if not api_key:
        raise ProviderError("Embedding provider is not configured")
    id = usage.intent(user_id, cfg.embedding_model, provider, operation, **refs)
    usage.dispatch(id)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            vectors, counts = await EMBEDDERS[provider](client, cfg, api_key, texts, operation)
        if len(vectors) != len(texts) or any(len(v) != cfg.embedding_dimensions for v in vectors):
            raise ProviderError("Invalid embedding response")
        usage.finalize(id, counts)
        return vectors
    except Exception:
        usage.finalize(id, status="unknown")
        raise ProviderError("Embedding request failed; usage may be unknown") from None
