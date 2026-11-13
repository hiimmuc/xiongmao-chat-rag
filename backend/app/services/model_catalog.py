"""Which chat models a user can pick: each provider's live model list plus MODEL_CATALOG_JSON.

For every provider the user has a key for (their own or the shared one), the provider is asked
for its models (free) and the list is cached for an hour. Entries in MODEL_CATALOG_JSON are always
listed first and win over a discovered model with the same API name, so they can set a label,
price or context size. Set MODEL_DISCOVERY=false to use MODEL_CATALOG_JSON alone.
"""

import hashlib
import logging
import re
import time

import httpx

from app.core.config import settings
from app.services.api_keys import PROVIDERS, api_key_for

TTL = 3600  # seconds a provider's list is reused
RETRY_AFTER = 60  # seconds before asking again after a failure
_cache = {}  # (provider, sha256 of key) -> (expires_at, models)

# OpenAI lists every model type under one endpoint; keep text chat models, drop dated snapshots.
OPENAI_CHAT = re.compile(r"^(gpt-[4-9]|o[1-9]|chatgpt-)")
OPENAI_SKIP = re.compile(
    r"audio|realtime|transcribe|tts|image|search|instruct|codex|computer-use|deep-research"
    r"|-\d{4}-\d{2}-\d{2}$|-\d{4}$"
)
# Gemini says which models can chat (generateContent); still drop media, embedding and pinned versions.
GEMINI_SKIP = re.compile(
    r"embedding|image|banana|tts|audio|transcribe|live|robotics|computer-use|customtools|aqa|-\d{3}$"
)


def _openai(key):
    r = httpx.get("https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + key}, timeout=10)
    r.raise_for_status()
    names = [m["id"] for m in r.json().get("data", [])]
    return [
        dict(id=n, provider="openai", label=n.replace("gpt-", "GPT-", 1), api_model=n)
        for n in names
        if OPENAI_CHAT.match(n) and not OPENAI_SKIP.search(n)
    ]


def _gemini(key):
    models, page = [], None
    while True:
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": key},
            params=dict(pageSize=1000, **({"pageToken": page} if page else {})),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        for m in data.get("models", []):
            name = m["name"].removeprefix("models/")
            if (
                name.startswith("gemini-")
                and "generateContent" in m.get("supportedGenerationMethods", [])
                and not GEMINI_SKIP.search(name)
            ):
                model = dict(id=name, provider="gemini", label=m.get("displayName") or name, api_model=name)
                if m.get("inputTokenLimit"):
                    model["context_tokens"] = m["inputTokenLimit"]
                models.append(model)
        page = data.get("nextPageToken")
        if not page:
            return models


LISTERS = {"openai": _openai, "gemini": _gemini}


def discover(provider, key):
    """The provider's chat models for this key, from cache when fresh. Empty if the provider fails."""
    slot = (provider, hashlib.sha256(key.encode()).hexdigest())
    cached = _cache.get(slot)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        models = sorted(LISTERS[provider](key), key=lambda m: m["id"], reverse=True)  # newest first
        _cache[slot] = (time.monotonic() + TTL, models)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logging.warning("model_discovery_failed provider=%s error=%s", provider, type(e).__name__)
        models = cached[1] if cached else []  # keep the last good list through a provider hiccup
        _cache[slot] = (time.monotonic() + RETRY_AFTER, models)
    return models


def catalog_for(db, user_id):
    """{model id: model} this user may choose from, configured entries first."""
    cfg = settings()
    models = dict(cfg.catalog())
    if not cfg.model_discovery:
        return models
    configured = {(m["provider"], m.get("api_model", m["id"])) for m in models.values()}
    for provider in PROVIDERS:
        key = api_key_for(db, user_id, provider)
        if not key:
            continue
        for m in discover(provider, key):
            if (provider, m["api_model"]) not in configured and m["id"] not in models:
                models[m["id"]] = m
    return models
