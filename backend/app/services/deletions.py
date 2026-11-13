"""Durable deletion requests: journal-first acceptance, idempotency and status.

1. The request is written to the deletion journal (write-once file) so it survives a crash.
2. `apply_intent` hides the resource at once and cancels its running answers (deletion_rules.py).
3. The worker later removes files and rows (worker/main.py: purge).
"""

import json

from fastapi import HTTPException
from sqlalchemy import select

from app.core import storage
from app.models import Deletion, Job, User, now, uid
from app.services.deletion_rules import RESOURCES


def apply_intent(db, entry):
    """Apply a journal entry: block the resource, cancel its answers and queue the purge. Idempotent per request."""
    existing = db.scalar(
        select(Deletion).where(
            Deletion.user_id == entry["user_id"], Deletion.request_id == entry["request_id"]
        )
    )
    if existing:
        return existing
    kind, rid, owner = entry["resource_type"], entry["resource_id"], entry["user_id"]
    RESOURCES[kind].block(db, rid, owner)
    d = Deletion(
        id=entry["id"],
        user_id=owner,
        subject=entry["subject"],
        request_id=entry["request_id"],
        resource_type=kind,
        resource_id=rid,
    )
    db.add(d)
    db.add(Job(kind="delete", resource_id=d.id))
    db.commit()
    return d


def accept_deletion(db, user, kind, rid, request_id):
    """Journal a deletion first, then apply it; returns the Deletion receipt.

    Replays of one idempotency key return the original outcome (and requeue a failed clean-up)."""
    rid = str(rid)
    request_id = str(request_id)
    # Serialize journal-first acceptance with other per-user state changes.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(
        select(Deletion).where(Deletion.user_id == user.id, Deletion.request_id == request_id)
    )
    if existing:
        if existing.resource_type != kind or existing.resource_id != rid:
            raise HTTPException(409, "Deletion key targets a different resource")
        if existing.status == "failed":
            existing.status = "accepted"
            existing.error_code = None
            db.add(Job(kind="delete", resource_id=existing.id))
            db.commit()
        return existing
    resource = RESOURCES[kind]
    row = db.get(resource.model, rid)
    if not row or resource.owner_of(row) != user.id:
        raise HTTPException(404, "Resource not found")
    entry = dict(
        schema_version=1,
        id=uid(),
        user_id=user.id,
        subject=user.subject,
        request_id=request_id,
        resource_type=kind,
        resource_id=rid,
        created_at=now().isoformat(),
    )
    key = f"deletions/{user.id}/{request_id}.json"
    try:
        written = storage.put(key, json.dumps(entry).encode(), journal=True, immutable=True)
        if not written:
            entry = json.loads(storage.get(key, True))
            if entry["resource_type"] != kind or entry["resource_id"] != rid:
                raise HTTPException(409, "Deletion key targets a different resource")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, dict(code="journal_unavailable", request_id=request_id)) from None
    try:
        return apply_intent(db, entry)
    except Exception:
        db.rollback()
        raise HTTPException(
            503,
            dict(
                code="deletion_outcome_unknown",
                request_id=request_id,
                message="Deletion may still proceed; retry with the same key",
            ),
        ) from None


def owned_deletion(db, user_id, id):
    d = db.scalar(select(Deletion).where(Deletion.id == str(id), Deletion.user_id == user_id))
    if not d:
        raise HTTPException(404, "Deletion request not found")
    return d
