"""Opt-in, billable smoke test using synthetic content and the API keys in .env. Never runs in CI.

    $env:RUN_LIVE_PROVIDER_TESTS = "1"
    $env:LIVE_MODELS = "gpt-4.1-mini,gemini-3.5-flash-lite"   # optional; default is MODEL_CATALOG_JSON
    .venv\\Scripts\\python -m pytest tests/test_live_providers.py -s
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_api import conversation, request

from app.core.config import settings
from app.models import User
from app.services.model_catalog import catalog_for

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_PROVIDER_TESTS") != "1",
    reason="Set RUN_LIVE_PROVIDER_TESTS=1 to authorize billable synthetic provider calls",
)


def test_live_model_switching_and_usage(api, monkeypatch):
    client, sessions, _ = api
    cfg = settings()
    monkeypatch.setattr(cfg, "model_discovery", True)  # the conftest turns it off for offline tests
    # Explicit opt-in covers synthetic test calls only; persisted policy settings stay unchanged.
    monkeypatch.setattr(cfg, "provider_retention_verified", True)
    monkeypatch.setattr(cfg, "max_output_tokens", 64)
    wanted = [m for m in os.environ.get("LIVE_MODELS", "").split(",") if m] or list(cfg.catalog())
    request(client, "GET", "/me")  # creates the test user
    with sessions() as db:
        available = catalog_for(db, db.scalar(select(User.id)))
    assert wanted, "Set LIVE_MODELS or MODEL_CATALOG_JSON"
    assert not (missing := set(wanted) - set(available)), f"Not offered for these keys: {missing}"
    models = [available[m] for m in wanted]
    cid = conversation(client, "Synthetic provider smoke")
    for model in models:
        response = request(
            client,
            "POST",
            f"/conversations/{cid}/generations",
            json={
                "request_id": str(uuid4()),
                "model_id": model["id"],
                "message": "Reply with the single word OK. No explanation.",
            },
        )
        assert response.status_code == 200
        assert "event: done" in response.text, f"{model['provider']}: stream did not complete"
        messages = request(client, "GET", f"/conversations/{cid}/messages").json()["items"]
        answer = messages[-1]
        assert answer["status"] == "completed", model["provider"]
        assert answer["model_id"] == model["id"]
        assert answer["content"].strip(), model["provider"]
        print(f"LIVE {model['provider']} {model.get('api_model', model['id'])}: completed")
    usage = request(client, "GET", "/usage/models").json()["items"]
    assert {row["model_id"] for row in usage} == {m["id"] for m in models}
