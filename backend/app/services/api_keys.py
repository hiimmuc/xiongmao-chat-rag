"""Provider API keys: a user's own encrypted key when set, otherwise the operator's shared key."""

import logging

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.config import settings
from app.models import UserKey, now

PROVIDERS = ("openai", "gemini")
PROBES = {
    "openai": ("https://api.openai.com/v1/models", lambda key: {"Authorization": "Bearer " + key}),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
        lambda key: {"x-goog-api-key": key},
    ),
}


def _cipher():
    key = settings().key_encryption_key
    return Fernet(key.encode()) if key else None


def storage_enabled():
    return bool(settings().key_encryption_key)


def shared_key(provider):
    return getattr(settings(), f"{provider}_api_key")


def _own_row(db, user_id, provider):
    return db.scalar(select(UserKey).where(UserKey.user_id == user_id, UserKey.provider == provider))


def api_key_for(db, user_id, provider):
    """The key to call `provider` with: the user's own if set and readable, else the shared one."""
    row, cipher = _own_row(db, user_id, provider), _cipher()
    if row and cipher:
        try:
            return cipher.decrypt(row.ciphertext.encode()).decode()
        except InvalidToken:
            logging.error("user_key_undecryptable provider=%s", provider)
    return shared_key(provider)


def provider_enabled(db, user_id, provider):
    return bool(api_key_for(db, user_id, provider))


def key_status(db, user_id, provider):
    """Where the key in effect comes from ("own", "shared" or "none"), never the key itself."""
    row = _own_row(db, user_id, provider)
    if row:
        return dict(provider=provider, source="own", hint=row.hint)
    return dict(provider=provider, source="shared" if shared_key(provider) else "none", hint=None)


def save_key(db, user_id, provider, api_key):
    """Encrypt and store the user's own key. Returns False when no encryption key is configured."""
    cipher = _cipher()
    if not cipher:
        return False
    row = _own_row(db, user_id, provider) or UserKey(user_id=user_id, provider=provider)
    row.ciphertext = cipher.encrypt(api_key.encode()).decode()
    row.hint = api_key[-4:]
    row.updated_at = now()
    db.add(row)
    db.commit()
    return True


def remove_key(db, user_id, provider):
    row = _own_row(db, user_id, provider)
    if row:
        db.delete(row)
        db.commit()


def probe(provider, key):
    """Ask the provider for its model list, which costs nothing, to check that the key works."""
    url, headers = PROBES[provider]
    try:
        status = httpx.get(url, headers=headers(key), timeout=10).status_code
    except httpx.HTTPError:
        return dict(ok=False, message="Could not reach the provider")
    if status == 200:
        return dict(ok=True, message="Connected")
    if status in (400, 401, 403):
        return dict(ok=False, message="The provider rejected this key")
    return dict(ok=False, message=f"The provider answered HTTP {status}")
