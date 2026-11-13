"""Per-user preferences, stored as one JSON column on the user row."""

from fastapi import HTTPException

from app.schemas import Preferences
from app.services.model_catalog import catalog_for

# Tone only. These never replace the grounding and citation rules added after them.
STYLES = {
    "default": "",
    "friendly": "Use a warm, encouraging and conversational tone.",
    "candid": "Be direct and candid. Give honest assessments, including disagreement, without padding.",
    "efficient": "Be concise and to the point. Prefer short answers and skip pleasantries.",
    "professional": "Use a polished, formal and precise tone suitable for business communication.",
    "analytical": "Reason step by step, weigh trade-offs and support claims with explicit logic.",
}


def preferences_for(user):
    return Preferences(**(user.preferences or {}))


def update_preferences(db, user, changes):
    """Merge a partial update into the stored preferences and return the result."""
    db.refresh(user, with_for_update=True)  # concurrent patches merge instead of overwriting each other
    merged = preferences_for(user).model_dump()
    # Ids already saved stay valid even if the catalog no longer lists them (a default whose provider has no key).
    if unknown := set(changes.get("models", [])) - set(catalog_for(db, user.id)) - set(merged["models"]):
        raise HTTPException(422, f"Unknown model: {sorted(unknown)[0]}")
    merged["notifications"].update(changes.pop("notifications", {}))
    merged.update(changes)
    user.preferences = Preferences(**merged).model_dump()
    db.commit()
    return user.preferences
