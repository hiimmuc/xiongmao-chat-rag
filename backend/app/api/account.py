"""/me: the signed-in user's profile and account deletion."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.api.deletions import deletion_json
from app.core.database import get_db
from app.core.security import current_user
from app.schemas import AccountDelete, ProfileUpdate
from app.services.auth import account_json, check_password, end_all_sessions
from app.services.deletions import accept_deletion

router = APIRouter(tags=["account"])


@router.get("/me")
def profile(user=Depends(current_user)):
    return account_json(user)


@router.patch("/me")
def update_profile(body: ProfileUpdate, user=Depends(current_user), db=Depends(get_db)):
    user.display_name = body.display_name
    db.commit()
    return account_json(user)


@router.delete("/me", status_code=202)
def delete_account(
    body: AccountDelete, idempotency_key: UUID = Header(), user=Depends(current_user), db=Depends(get_db)
):
    """Needs the account password. Signs out every browser once the deletion is accepted."""
    check_password(user, body.password)
    deletion = accept_deletion(db, user, "account", user.id, idempotency_key)
    end_all_sessions(db, user)
    return deletion_json(deletion)
