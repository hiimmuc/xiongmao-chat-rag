"""/models: the models this user can pick right now."""

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user
from app.services.api_keys import provider_enabled
from app.services.model_catalog import catalog_for

router = APIRouter(tags=["models"])


@router.get("/models")
def models(user=Depends(current_user), db=Depends(get_db)):
    cfg = settings()
    return dict(
        items=[
            dict(id=m["id"], provider=m["provider"], label=m.get("label", m["id"]))
            for m in catalog_for(db, user.id).values()
            if provider_enabled(db, user.id, m["provider"]) and cfg.provider_retention_verified
        ],
        processing_policy_url=cfg.provider_policy_url,
    )
