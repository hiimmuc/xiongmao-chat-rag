"""/me/keys: save, remove and test the user's own provider API keys. Keys are never returned."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.core.security import current_user
from app.schemas import KeyBody, KeyTest
from app.services import api_keys

router = APIRouter(tags=["account"])
Provider = Literal["openai", "gemini"]


@router.get("/me/keys")
def list_keys(user=Depends(current_user), db=Depends(get_db)):
    return dict(
        items=[api_keys.key_status(db, user.id, p) for p in api_keys.PROVIDERS],
        storage_enabled=api_keys.storage_enabled(),
    )


@router.put("/me/keys/{provider}")
def save_key(provider: Provider, body: KeyBody, user=Depends(current_user), db=Depends(get_db)):
    if not api_keys.save_key(db, user.id, provider, body.api_key):
        raise HTTPException(503, "Key storage is not configured")
    return api_keys.key_status(db, user.id, provider)


@router.delete("/me/keys/{provider}")
def remove_key(provider: Provider, user=Depends(current_user), db=Depends(get_db)):
    api_keys.remove_key(db, user.id, provider)
    return api_keys.key_status(db, user.id, provider)


@router.post("/me/keys/{provider}/test")
def test_key(provider: Provider, body: KeyTest, user=Depends(current_user), db=Depends(get_db)):
    """Test the supplied key, or the key currently in effect when none is supplied."""
    key = body.api_key or api_keys.api_key_for(db, user.id, provider)
    if not key:
        return dict(ok=False, message="No key is configured")
    return api_keys.probe(provider, key)
