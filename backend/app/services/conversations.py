"""Conversations: ownership, listing, renaming, document selection and message history."""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.models import Conversation, Document, Generation, Message, now
from app.services.projects import in_scope, resolve_project
from app.services.usage import usage_briefs


def owned_conversation(db, user_id, id, lock=False):
    """The active conversation owned by `user_id`, optionally row-locked; raises 404 otherwise."""
    q = select(Conversation).where(
        Conversation.id == str(id), Conversation.user_id == user_id, Conversation.state == "active"
    )
    row = db.scalar(q.with_for_update() if lock else q)
    if not row:
        raise HTTPException(404, "Conversation not found")
    return row


def list_conversations(db, user, project_id, search, cursor, limit):
    """One page of the project's chats, newest first. Returns (rows, next_cursor)."""
    project = resolve_project(db, user, project_id)
    q = select(Conversation).where(
        Conversation.user_id == user.id, Conversation.project_id == project.id, Conversation.state == "active"
    )
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.where(Conversation.title.ilike("%" + escaped + "%", escape="\\"))
    if cursor:
        try:
            stamp, id = cursor.split("|")
            stamp = datetime.fromisoformat(stamp)
            UUID(id)
        except ValueError:
            raise HTTPException(422, "Invalid cursor") from None
        q = q.where(
            or_(Conversation.updated_at < stamp, and_(Conversation.updated_at == stamp, Conversation.id < id))
        )
    rows = db.scalars(
        q.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return rows, f"{rows[-1].updated_at.isoformat()}|{rows[-1].id}" if more else None


def create_conversation(db, user, project_id, title):
    project = resolve_project(db, user, project_id)
    c = Conversation(user_id=user.id, project_id=project.id, title=title)
    db.add(c)
    db.commit()
    return c


def update_conversation(db, user, id, title=None, document_ids=None):
    """Rename and/or choose which ready documents in scope the chat's answers may use."""
    c = owned_conversation(db, user.id, id, lock=True)
    if title is not None:
        c.title = title
    if document_ids is not None:
        ids = list(dict.fromkeys(str(x) for x in document_ids))
        docs = db.scalars(
            select(Document).where(
                Document.id.in_(ids),
                Document.user_id == user.id,
                *in_scope(c),
                Document.state == "ready",
            )
        ).all()
        if len(docs) != len(ids):
            raise HTTPException(404, "Selected document unavailable")
        c.document_ids = ids
    c.updated_at = now()
    db.commit()
    return c


def message_page(db, c, cursor, limit):
    """Messages after sequence `cursor`. Returns ([(message, generation or None, usage or None)], next_cursor)."""
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == c.id, Message.sequence > cursor)
        .order_by(Message.sequence)
        .limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    gens = {
        g.assistant_message_id: g
        for g in db.scalars(
            select(Generation).where(Generation.assistant_message_id.in_([m.id for m in rows]))
        )
    }
    usages = usage_briefs(db, [g.id for g in gens.values()])
    items = []
    for m in rows:
        g = gens.get(m.id)
        items.append((m, g, usages.get(g.id) if g else None))
    return items, str(rows[-1].sequence) if more else None
