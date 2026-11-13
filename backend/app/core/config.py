"""Environment-driven settings and the model catalog."""

import json
import logging
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    app_env: str = "local"
    # Local default matches scripts/local_db.py; the server sets its own URL in .env.
    database_url: str = "postgresql+psycopg://chatbot:local-development-only@localhost:55432/chatbot"
    cors_origins: str = "http://localhost:5173"
    jwt_secret: str = ""  # signs access tokens; required in production (32+ characters)
    access_token_minutes: int = 15
    refresh_token_days: int = 30  # a browser stays signed in this long without using the app
    storage_dir: str = ".local-storage"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    model_catalog_json: str = "[]"  # fixed entries (label, price, context); listed first
    model_discovery: bool = True  # also list every chat model each provider offers for the key in use
    key_encryption_key: str = ""  # Fernet key; user-supplied API keys cannot be stored without it
    embedding_provider: str = "gemini"  # "gemini" or "openai"; changing it requires re-indexing
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    max_upload_bytes: int = 10485760
    max_document_pages: int = 100
    max_user_files: int = 100
    max_user_bytes: int = 104857600
    max_output_tokens: int = 2048
    generation_timeout: int = 120
    provider_retention_verified: bool = False
    provider_policy_url: str = ""

    def catalog(self):
        models = json.loads(self.model_catalog_json)
        return {m["id"]: m for m in models if m.get("provider") in ("openai", "gemini")}


@lru_cache
def settings():
    cfg = Settings()
    if len(cfg.jwt_secret) < 32:
        if cfg.app_env == "production":
            raise RuntimeError("Production requires JWT_SECRET with at least 32 characters")
        # Development only: a fresh secret per run. Access tokens then end on restart,
        # but the browser's refresh cookie still signs it back in.
        logging.warning("JWT_SECRET not set; using a temporary one")
        cfg.jwt_secret = secrets.token_urlsafe(32)
    return cfg
