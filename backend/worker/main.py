"""Serial worker: document ingestion, resource deletion and journal reconciliation."""

import asyncio
import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import delete, select

from app.core import database, storage
from app.models import Chunk, Deletion, Document, Job, User, now
from app.services.deletion_rules import RESOURCES
from app.services.deletions import apply_intent
from app.services.ingestion import chunk_text, isolated_parse
from app.services.providers import ProviderError, embed

stopping = False


async def ingest(id):
    """Extract, chunk and embed one queued document, publishing chunks only while it stays eligible."""
    with database.Session() as db:
        doc = db.get(Document, id)
        if not doc or doc.state != "queued":
            return
        user = db.get(User, doc.user_id)
        if not user or user.state != "active":
            return
        doc.state = "processing"
        db.commit()
        key, owner, version = doc.object_key, doc.user_id, doc.version
    pages = isolated_parse(key, storage.get(key))
    pieces = [(page, chunk) for page, text in pages for chunk in chunk_text(text)]
    vectors = []
    for offset in range(0, len(pieces), 32):
        with database.Session() as db:
            live = db.get(Document, id)
            u = db.get(User, owner)
            if not live or live.state != "processing" or not u or u.state != "active":
                return
        vectors.extend(
            await embed(
                [x[1] for x in pieces[offset : offset + 32]], owner, "document_embedding", document_id=id
            )
        )
    with database.Session() as db:
        live = db.scalar(select(Document).where(Document.id == id).with_for_update())
        u = db.get(User, owner)
        if not live or live.state != "processing" or not u or u.state != "active":
            return
        db.execute(delete(Chunk).where(Chunk.document_id == id))
        for i, ((page, text), vector) in enumerate(zip(pieces, vectors)):
            db.add(
                Chunk(
                    document_id=id,
                    project_id=live.project_id,
                    version=version,
                    ordinal=i,
                    page=page,
                    content=text,
                    embedding=vector,
                )
            )
        live.state = "ready"
        live.error_code = None
        db.commit()


def purge(deletion_id):
    """Remove a deleted resource's files and rows once no answer still uses it. False means retry later."""
    with database.Session() as db:
        d = db.get(Deletion, deletion_id)
        if not d or d.status == "completed":
            return True
        resource = RESOURCES[d.resource_type]
        if resource.active_runs(db, d.resource_id, d.user_id):
            return False
        d.status = "processing"
        db.commit()
        for doc in resource.files(db, d.resource_id, d.user_id):
            storage.remove(doc.object_key)
        row = db.get(resource.model, d.resource_id)
        if row:
            db.delete(row)
        d.status = "completed"
        d.completed_at = now()
        d.error_code = None
        db.commit()
    return True


def reconcile_journal():
    with database.Session() as db:
        for entry in storage.journal_entries():
            apply_intent(db, entry)
        # Expire upload reservations, without replaying any paid processing job.
        for doc in db.scalars(
            select(Document).where(
                Document.state == "uploading", Document.created_at < now() - timedelta(hours=1)
            )
        ).all():
            storage.remove(doc.object_key)
            db.delete(doc)
        db.commit()


def run_once():
    with database.Session() as db:
        job = db.scalar(
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status = "processing"
        db.commit()
        id, kind, resource = job.id, job.kind, job.resource_id
    try:
        if kind == "ingest":
            asyncio.run(ingest(resource))
            done = True
        elif kind == "delete":
            done = purge(resource)
        else:
            raise ValueError("invalid_job")
        with database.Session() as db:
            job = db.get(Job, id)
            if job:
                job.status = "completed" if done else "queued"
                db.commit()
    except Exception as error:
        with database.Session() as db:
            job = db.get(Job, id)
            if job:
                job.status = "failed"
                job.error_code = "processing_failed"
            doc = db.get(Document, resource) if kind == "ingest" else None
            if doc and doc.state not in ("deleting", "deleted"):
                doc.state = "failed"
                doc.error_code = (
                    "embedding_failed" if isinstance(error, ProviderError) else "invalid_document"
                )
            if kind == "delete":
                d = db.get(Deletion, resource)
                if d:
                    d.status = "failed"
                    d.error_code = "cleanup_failed"
            db.commit()
        logging.error("worker_failed job_id=%s type=%s", id, type(error).__name__)
    return True


def stop(signum, frame):
    global stopping
    stopping = True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_reconcile = 0
    # One worker is assumed; add fencing before running more than one.
    while not stopping:
        try:
            if time.monotonic() - last_reconcile > 60:
                reconcile_journal()
                last_reconcile = time.monotonic()
            worked = run_once()
        except Exception as error:
            logging.error("worker_loop_failed type=%s", type(error).__name__, exc_info=error)
            worked = False
        time.sleep(1 if worked else 3)


if __name__ == "__main__":
    main()
