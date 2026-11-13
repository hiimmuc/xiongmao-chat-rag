"""Documents: upload checks and quotas, listing, renaming, download and retrying ingestion.

Text extraction and embedding happen later in the worker (ingestion.py).
"""

from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core import storage
from app.core.config import settings
from app.models import Document, Job, User, uid
from app.services.conversations import owned_conversation
from app.services.projects import resolve_project

TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


def owned_document(db, owner, id):
    d = db.scalar(
        select(Document).where(
            Document.id == str(id), Document.user_id == owner, Document.state.not_in(("deleting", "deleted"))
        )
    )
    if not d:
        raise HTTPException(404, "Document not found")
    return d


def session_chat(db, user, project, conversation_id):
    """Free-chat uploads belong to one chat; project documents never do."""
    if project.kind != "free":
        if conversation_id:
            raise HTTPException(422, "Documents in a project are shared by its chats")
        return None
    if not conversation_id:
        raise HTTPException(422, "Free chats need a conversation for session documents")
    c = owned_conversation(db, user.id, conversation_id)
    if c.project_id != project.id:
        raise HTTPException(404, "Conversation not found")
    return c


def check_file(filename, data):
    """Validate name, size and type of an upload. Returns (safe name, suffix)."""
    name = Path((filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES or len(name) > 255:
        raise HTTPException(422, "Use text PDF, TXT or Markdown")
    if not data or len(data) > settings().max_upload_bytes:
        raise HTTPException(413, "File empty or exceeds 10 MiB")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF")
    if suffix != ".pdf":
        try:
            text = data.decode("utf-8")
            if "\x00" in text or not text.strip():
                raise ValueError()
        except (UnicodeError, ValueError):
            raise HTTPException(422, "UTF-8 text required") from None
    return name, suffix


def upload(db, user, filename, data, project_id=None, conversation_id=None):
    """Store an upload and queue it for the worker. Returns the new Document."""
    cfg = settings()
    name, suffix = check_file(filename, data)
    project = resolve_project(db, user, project_id)
    session = session_chat(db, user, project, conversation_id)
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    count, size = db.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.bytes), 0)).where(
            Document.user_id == user.id
        )
    ).one()
    if count >= cfg.max_user_files or size + len(data) > cfg.max_user_bytes:
        raise HTTPException(413, "Document storage limit reached")
    id = uid()
    key = f"documents/{user.id}/{id}{suffix}"
    doc = Document(
        id=id,
        user_id=user.id,
        project_id=project.id,
        conversation_id=session.id if session else None,
        name=name,
        mime=TYPES[suffix],
        bytes=len(data),
        object_key=key,
    )
    db.add(doc)
    db.flush()
    try:
        storage.put(key, data)
        doc.state = "queued"
        db.add(Job(kind="ingest", resource_id=id))
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.remove(key)
        except Exception:
            pass
        raise HTTPException(503, "Upload could not be stored; retry later") from None
    return doc


def list_documents(db, user, project_id, conversation_id, cursor, limit):
    """One page of documents in a project (or a free chat). Returns (rows, next_cursor)."""
    project = resolve_project(db, user, project_id)
    session = session_chat(db, user, project, conversation_id)
    q = select(Document).where(
        Document.conversation_id == (session.id if session else None),
        Document.user_id == user.id,
        Document.project_id == project.id,
        Document.state.not_in(("deleting", "deleted")),
    )
    if cursor:
        try:
            UUID(cursor)
        except ValueError:
            raise HTTPException(422, "Invalid cursor") from None
        q = q.where(Document.id < cursor)
    rows = db.scalars(q.order_by(Document.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return rows, rows[-1].id if more else None


def rename(db, user, id, name):
    d = owned_document(db, user.id, id)
    d.name = name
    db.commit()
    return d


def read_file(db, user, id):
    """The document row and its original bytes."""
    d = owned_document(db, user.id, id)
    try:
        return d, storage.get(d.object_key)
    except Exception:
        raise HTTPException(503, "File storage unavailable") from None


def retry(db, user, id):
    """Queue a failed document for ingestion again."""
    d = owned_document(db, user.id, id)
    if d.state != "failed" or d.error_code == "upload_failed":
        raise HTTPException(409, "Document cannot be retried")
    d.state = "queued"
    d.error_code = None
    db.add(Job(kind="ingest", resource_id=d.id))
    db.commit()
    return d
