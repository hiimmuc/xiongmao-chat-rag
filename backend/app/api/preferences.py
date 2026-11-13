"""/me/preferences: appearance, response style, notifications and model shortlist."""

from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.security import current_user
from app.schemas import PreferencesUpdate
from app.services.preferences import preferences_for, update_preferences

router = APIRouter(tags=["account"])


@router.get("/me/preferences")
def get_preferences(user=Depends(current_user)):
    return preferences_for(user).model_dump()


@router.patch("/me/preferences")
def patch_preferences(body: PreferencesUpdate, user=Depends(current_user), db=Depends(get_db)):
    return update_preferences(db, user, body.model_dump(exclude_none=True))
