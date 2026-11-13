"""/deletions/{id}: status of a deletion request. Each resource's DELETE route lives with the resource."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.security import current_user
from app.services.deletions import owned_deletion

router = APIRouter(tags=["deletions"])


def deletion_json(d):
    """The receipt every DELETE route returns."""
    return dict(
        deletion_id=d.id,
        id=d.id,
        resource_type=d.resource_type,
        status=d.status,
        accepted_at=d.created_at,
        completed_at=d.completed_at,
        error_code=d.error_code,
    )


@router.get("/deletions/{id}")
def deletion_status(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return deletion_json(owned_deletion(db, user.id, id))
