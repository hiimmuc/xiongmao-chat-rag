"""/conversations: list, create, rename, choose documents, read messages, branch and delete chats."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.api.deletions import deletion_json
from app.core.database import get_db
from app.core.security import current_user
from app.schemas import BranchBody, ConversationCreate, ConversationUpdate
from app.services import conversations
from app.services.branching import branch_conversation
from app.services.deletions import accept_deletion

router = APIRouter(tags=["conversations"])


def conversation_json(c):
    return dict(
        id=c.id,
        title=c.title,
        state=c.state,
        project_id=c.project_id,
        document_ids=c.document_ids,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def message_json(m, g, usage):
    return dict(
        id=m.id,
        sequence=m.sequence,
        role=m.role,
        content=m.content,
        generation_id=g.id if g else None,
        status=g.status if g else None,
        model_id=g.model_id if g else None,
        provider=g.provider if g else None,
        citations=g.sources if g else [],
        usage=usage,
    )


@router.get("/conversations")
def list_conversations(
    search: str = Query("", max_length=120),
    project_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    rows, next_cursor = conversations.list_conversations(db, user, project_id, search, cursor, limit)
    return dict(items=[conversation_json(c) for c in rows], next_cursor=next_cursor)


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, user=Depends(current_user), db=Depends(get_db)):
    return conversation_json(conversations.create_conversation(db, user, body.project_id, body.title))


@router.get("/conversations/{id}")
def get_conversation(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return conversation_json(conversations.owned_conversation(db, user.id, id))


@router.patch("/conversations/{id}")
def patch_conversation(id: UUID, body: ConversationUpdate, user=Depends(current_user), db=Depends(get_db)):
    c = conversations.update_conversation(db, user, id, body.title, body.document_ids)
    return conversation_json(c)


@router.get("/conversations/{id}/messages")
def messages(
    id: UUID,
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    c = conversations.owned_conversation(db, user.id, id)
    items, next_cursor = conversations.message_page(db, c, cursor, limit)
    return dict(items=[message_json(*item) for item in items], next_cursor=next_cursor)


@router.post("/conversations/{id}/branch", status_code=201)
def branch(id: UUID, body: BranchBody, user=Depends(current_user), db=Depends(get_db)):
    c = conversations.owned_conversation(db, user.id, id)
    return conversation_json(branch_conversation(db, user, c, body.message_id))


@router.delete("/conversations/{id}", status_code=202)
def delete_conversation(
    id: UUID, idempotency_key: UUID = Header(), user=Depends(current_user), db=Depends(get_db)
):
    return deletion_json(accept_deletion(db, user, "conversation", id, idempotency_key))
