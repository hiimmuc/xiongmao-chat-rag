"""/documents: upload, list, rename, download, retry and delete."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, UploadFile
from fastapi.responses import Response

from app.api.deletions import deletion_json
from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user
from app.schemas import DocumentUpdate
from app.services import documents
from app.services.deletions import accept_deletion

router = APIRouter(tags=["documents"])


def document_json(d):
    return dict(
        id=d.id,
        name=d.name,
        mime=d.mime,
        project_id=d.project_id,
        conversation_id=d.conversation_id,
        bytes=d.bytes,
        state=d.state,
        version=d.version,
        error_code=d.error_code,
        created_at=d.created_at,
    )


@router.post("/documents", status_code=202)
def upload_document(
    file: UploadFile,
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    user=Depends(current_user),
    db=Depends(get_db),
):
    # Sync on purpose: the PDF check runs in a child process, so FastAPI runs this in its thread pool.
    data = file.file.read(settings().max_upload_bytes + 1)  # one extra byte detects oversize files
    file.file.close()
    return document_json(documents.upload(db, user, file.filename, data, project_id, conversation_id))


@router.get("/documents")
def list_documents(
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    rows, next_cursor = documents.list_documents(db, user, project_id, conversation_id, cursor, limit)
    return dict(items=[document_json(d) for d in rows], next_cursor=next_cursor)


@router.get("/documents/{id}")
def get_document(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return document_json(documents.owned_document(db, user.id, id))


@router.patch("/documents/{id}")
def rename_document(id: UUID, body: DocumentUpdate, user=Depends(current_user), db=Depends(get_db)):
    return document_json(documents.rename(db, user, id, body.name))


@router.get("/documents/{id}/download")
def download_document(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    d, data = documents.read_file(db, user, id)
    return Response(
        data,
        media_type=d.mime,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(d.name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/documents/{id}/retry", status_code=202)
def retry_document(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return document_json(documents.retry(db, user, id))


@router.delete("/documents/{id}", status_code=202)
def delete_document(
    id: UUID, idempotency_key: UUID = Header(), user=Depends(current_user), db=Depends(get_db)
):
    return deletion_json(accept_deletion(db, user, "document", id, idempotency_key))
