"""Copy a conversation up to one finished answer into a new chat."""

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Conversation, Generation, Message, uid


def branch_conversation(db, user, c, cut_id):
    """Return a new chat holding `c` up to the answer `cut_id`, with the completed turns as context."""
    cut = db.scalar(select(Message).where(Message.id == str(cut_id), Message.conversation_id == c.id))
    if not cut or cut.role != "assistant":
        raise HTTPException(404, "Answer not found")
    history = db.scalars(
        select(Message)
        .where(Message.conversation_id == c.id, Message.sequence <= cut.sequence)
        .order_by(Message.sequence)
    ).all()
    done = db.scalars(
        select(Generation)
        .where(
            Generation.conversation_id == c.id,
            Generation.status == "completed",
            Generation.assistant_message_id.in_([m.id for m in history]),
        )
        .order_by(Generation.created_at)
    ).all()
    if cut.id not in {g.assistant_message_id for g in done}:
        raise HTTPException(404, "Answer not found")
    # Of several answers to one question (regenerated), only the newest up to the cut is kept.
    answers = {g.assistant_message_id: g for g in done}
    newest = {g.user_message_id: g.assistant_message_id for g in done}
    kept = [
        m
        for m in history
        if m.role == "user" or (m.id in answers and newest[answers[m.id].user_message_id] == m.id)
    ]

    copy = Conversation(
        user_id=user.id,
        project_id=c.project_id,
        title=("Branch: " + c.title)[:120],
        document_ids=c.document_ids,
    )
    db.add(copy)
    db.flush()
    moved = {
        m.id: Message(conversation_id=copy.id, sequence=i, role=m.role, content=m.content)
        for i, m in enumerate(kept, start=1)
    }
    db.add_all(moved.values())
    db.flush()
    for g in done:
        if g.assistant_message_id in moved:
            db.add(
                Generation(
                    user_id=user.id,
                    conversation_id=copy.id,
                    user_message_id=moved[g.user_message_id].id,
                    assistant_message_id=moved[g.assistant_message_id].id,
                    request_id=uid(),
                    payload_hash=g.payload_hash,
                    model_id=g.model_id,
                    provider=g.provider,
                    status="completed",
                    sources=g.sources,
                    document_versions=g.document_versions,
                )
            )
    db.commit()
    return copy
