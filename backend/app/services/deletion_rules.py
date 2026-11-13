"""Deletion rules per resource type: what to hide, which running answers to stop, which files to remove."""

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select, update

from app.models import Conversation, Document, Generation, Project, User

RUNNING = ("pending", "streaming")


def _cancel(db, *conditions):
    db.execute(update(Generation).where(*conditions).values(cancel_requested=True))


def _delete_state(db, model, rid, owner, owner_column="user_id"):
    db.execute(
        update(model).where(model.id == rid, getattr(model, owner_column) == owner).values(state="deleting")
    )


def _in_project(rid):
    return Generation.conversation_id.in_(select(Conversation.id).where(Conversation.project_id == rid))


def _block_account(db, rid, owner):
    _delete_state(db, User, rid, owner, "id")
    db.execute(update(Conversation).where(Conversation.user_id == owner).values(state="deleting"))
    db.execute(update(Document).where(Document.user_id == owner).values(state="deleting"))
    _cancel(db, Generation.user_id == owner)


def _block_project(db, rid, owner):
    _delete_state(db, Project, rid, owner)
    for model in (Conversation, Document):
        db.execute(
            update(model).where(model.project_id == rid, model.user_id == owner).values(state="deleting")
        )
    _cancel(db, Generation.user_id == owner, _in_project(rid))


def _block_conversation(db, rid, owner):
    _delete_state(db, Conversation, rid, owner)
    _cancel(db, Generation.conversation_id == rid, Generation.user_id == owner)
    # Documents uploaded into a free chat die with it.
    db.execute(
        update(Document)
        .where(Document.conversation_id == rid, Document.user_id == owner)
        .values(state="deleting")
    )


def _block_document(db, rid, owner):
    _delete_state(db, Document, rid, owner)
    for c in db.scalars(select(Conversation).where(Conversation.user_id == owner)):
        c.document_ids = [x for x in c.document_ids if x != rid]
    for g in db.scalars(select(Generation).where(Generation.user_id == owner)):
        if g.status in RUNNING and _uses_document(g, rid):
            g.cancel_requested = True
        g.sources = [
            dict(id=x["id"], document_id=rid, deleted=True, name="Source deleted")
            if x.get("document_id") == rid
            else x
            for x in g.sources
        ]


def _uses_document(g, rid):
    return any(x["id"] == rid for x in g.document_versions)


@dataclass(frozen=True)
class Resource:
    model: type
    owner_of: Callable  # row -> owner user id
    block: Callable  # (db, rid, owner): hide the resource and stop its answers
    running: Callable  # (rid, owner) -> Generation conditions for answers it affects
    documents: Callable  # (rid, owner) -> Document conditions for files to remove
    touches: Callable = lambda g, rid: True  # extra filter on running answers

    def active_runs(self, db, rid, owner):
        q = select(Generation).where(Generation.status.in_(RUNNING), *self.running(rid, owner))
        return [g for g in db.scalars(q) if self.touches(g, rid)]

    def files(self, db, rid, owner):
        return db.scalars(select(Document).where(*self.documents(rid, owner))).all()


RESOURCES = {
    "account": Resource(
        User,
        lambda row: row.id,
        _block_account,
        lambda rid, owner: [Generation.user_id == owner],
        lambda rid, owner: [Document.user_id == owner],
    ),
    "project": Resource(
        Project,
        lambda row: row.user_id,
        _block_project,
        lambda rid, owner: [_in_project(rid)],
        lambda rid, owner: [Document.project_id == rid],
    ),
    "conversation": Resource(
        Conversation,
        lambda row: row.user_id,
        _block_conversation,
        lambda rid, owner: [Generation.conversation_id == rid],
        lambda rid, owner: [Document.conversation_id == rid],
    ),
    "document": Resource(
        Document,
        lambda row: row.user_id,
        _block_document,
        lambda rid, owner: [Generation.user_id == owner],
        lambda rid, owner: [Document.id == rid],
        _uses_document,
    ),
}
