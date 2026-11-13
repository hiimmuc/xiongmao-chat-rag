"""Answers (generations): admission checks, starting a turn, cancelling and citation lookup.

Streaming the answer itself happens in chat_stream.py.
"""

import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Document, Generation, Message, User, now
from app.services.api_keys import provider_enabled
from app.services.chat_stream import TERMINAL
from app.services.conversations import owned_conversation
from app.services.model_catalog import catalog_for
from app.services.projects import in_scope

RETRYABLE = TERMINAL
MAX_ACTIVE_PER_USER = 2
MAX_PER_MINUTE = 10
MAX_PER_DAY = 100


def owned_generation(db, owner, id):
    g = db.scalar(select(Generation).where(Generation.id == str(id), Generation.user_id == owner))
    if not g:
        raise HTTPException(404, "Generation not found")
    owned_conversation(db, owner, g.conversation_id)
    return g


def cancel(db, owner, id):
    g = owned_generation(db, owner, id)
    if g.status not in TERMINAL:
        g.cancel_requested = True
    db.commit()
    return g


def citation(db, owner, id, citation_id):
    """One source of an answer, as long as its document still exists."""
    g = owned_generation(db, owner, id)
    source = next((x for x in g.sources if x["id"] == citation_id), None)
    if not source:
        raise HTTPException(404, "Source not found")
    d = db.get(Document, source["document_id"])
    if not d or d.user_id != owner or d.state != "ready":
        raise HTTPException(404, "Source deleted or unavailable")
    return source


def check_capacity(db, user, c):
    """Reject when the user or chat already has a running answer, or a request limit is hit."""
    active = db.scalars(
        select(Generation).where(Generation.user_id == user.id, Generation.status.not_in(TERMINAL))
    ).all()
    if len(active) >= MAX_ACTIVE_PER_USER or any(g.conversation_id == c.id for g in active):
        raise HTTPException(409, "Another answer is already running")

    def since(moment):
        return db.scalar(
            select(func.count())
            .select_from(Generation)
            .where(Generation.user_id == user.id, Generation.created_at >= moment)
        )

    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    if since(now() - timedelta(minutes=1)) >= MAX_PER_MINUTE or since(midnight) >= MAX_PER_DAY:
        raise HTTPException(429, "Request limit reached; try later")


def selected_documents(db, user, c):
    docs = db.scalars(
        select(Document).where(
            Document.id.in_(c.document_ids),
            Document.user_id == user.id,
            *in_scope(c),
            Document.state == "ready",
        )
    ).all()
    if len(docs) != len(c.document_ids):
        raise HTTPException(404, "Selected document unavailable")
    return docs


def question_for(db, user, c, body):
    """The user message this answer responds to: a new one, or the original of a retried turn."""
    if not body.retry_of:
        last = db.scalar(
            select(func.coalesce(func.max(Message.sequence), 0)).where(Message.conversation_id == c.id)
        )
        message = Message(conversation_id=c.id, sequence=last + 1, role="user", content=body.message)
        db.add(message)
        db.flush()
        return message
    previous = db.scalar(
        select(Generation).where(
            Generation.id == str(body.retry_of),
            Generation.user_id == user.id,
            Generation.conversation_id == c.id,
        )
    )
    if not previous or previous.status not in RETRYABLE:
        raise HTTPException(409, "Only finished answers can be regenerated")
    original = db.get(Message, previous.user_message_id)
    later = db.scalar(
        select(Message.id)
        .where(Message.conversation_id == c.id, Message.role == "user", Message.sequence > original.sequence)
        .limit(1)
    )
    if later:
        raise HTTPException(409, "Start a new message after later turns")
    return original


def start_generation(db, user, conversation_id, body):
    """Admit a new answer and save its pending rows. Returns (generation, model, replayed).

    A repeated `request_id` with the same content returns the original generation with replayed=True."""
    # Serialize every admission decision for this user across API instances.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    c = owned_conversation(db, user.id, conversation_id, lock=True)
    payload = body.model_dump(mode="json", exclude_none=True)
    digest = hashlib.sha256(
        json.dumps(dict(conversation_id=c.id, **payload), sort_keys=True).encode()
    ).hexdigest()
    prior = db.scalar(
        select(Generation).where(Generation.user_id == user.id, Generation.request_id == str(body.request_id))
    )
    if prior:
        if prior.payload_hash != digest:
            raise HTTPException(409, "Request ID has different content")
        return prior, None, True
    model = catalog_for(db, user.id).get(body.model_id)
    if not model:
        raise HTTPException(422, "Unsupported model")
    if not provider_enabled(db, user.id, model["provider"]) or not settings().provider_retention_verified:
        raise HTTPException(503, "Provider unavailable or processing policy has not been reviewed")
    check_capacity(db, user, c)
    docs = selected_documents(db, user, c)
    last = db.scalar(
        select(func.coalesce(func.max(Message.sequence), 0)).where(Message.conversation_id == c.id)
    )
    original = question_for(db, user, c, body)
    answer_at = last + (1 if body.retry_of else 2)
    assistant = Message(conversation_id=c.id, sequence=answer_at, role="assistant", content="")
    db.add(assistant)
    db.flush()
    g = Generation(
        user_id=user.id,
        conversation_id=c.id,
        user_message_id=original.id,
        assistant_message_id=assistant.id,
        request_id=str(body.request_id),
        payload_hash=digest,
        model_id=body.model_id,
        provider=model["provider"],
        document_versions=[dict(id=d.id, version=d.version) for d in docs],
    )
    db.add(g)
    if c.title == "New chat":
        c.title = original.content[:70]
    c.updated_at = now()
    db.commit()
    return g, model, False
