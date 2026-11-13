"""Find the document passages most relevant to a question (vector search in pgvector)."""

import tiktoken
from sqlalchemy import or_, select

from app.core import database
from app.models import Chunk, Conversation, Document, User
from app.services.providers import embed

TOP_K = 5


def retrieval_query(question, history):
    """The question plus a bounded tail of the preceding turns, so follow-ups keep their referents."""
    if not history:
        return question
    enc = tiktoken.get_encoding("cl100k_base")
    context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    bounded = enc.decode(enc.encode(context, disallowed_special=())[-1024:])
    return f"{bounded}\nCurrent question: {question}" if bounded else question


async def retrieve(question, generation):
    """Top passages for `question` from the documents snapshotted on `generation`, within its project and chat.

    Raises:
        ValueError: If the account or a snapshotted document is no longer usable."""
    snapshots = generation.document_versions
    if not snapshots:
        return []
    vector = (
        await embed(
            [question],
            generation.user_id,
            "query_embedding",
            conversation_id=generation.conversation_id,
            generation_id=generation.id,
        )
    )[0]
    with database.Session() as db:
        user = db.get(User, generation.user_id)
        if not user or user.state != "active":
            raise ValueError("Account unavailable")
        chat = db.get(Conversation, generation.conversation_id)
        project_id = chat.project_id
        session = or_(Document.conversation_id.is_(None), Document.conversation_id == chat.id)
        docs = db.scalars(
            select(Document).where(
                Document.id.in_([x["id"] for x in snapshots]),
                Document.user_id == generation.user_id,
                Document.project_id == project_id,
                session,
                Document.state == "ready",
            )
        ).all()
        if {(d.id, d.version) for d in docs} != {(x["id"], x["version"]) for x in snapshots}:
            raise ValueError("Selected document unavailable")
        distance = Chunk.embedding.op("<=>")(vector)
        q = (
            select(Chunk, Document)
            .join(Document)
            .where(
                Document.user_id == generation.user_id,
                Document.project_id == project_id,
                Chunk.project_id == project_id,
                session,
                Document.state == "ready",
                Chunk.version == Document.version,
                Document.id.in_([x["id"] for x in snapshots]),
            )
            .order_by(distance)
            .limit(TOP_K)
        )
        rows = db.execute(q).all()
        return [
            dict(
                id=str(i + 1),
                document_id=d.id,
                version=c.version,
                name=d.name,
                page=c.page,
                ordinal=c.ordinal,
                snippet=c.content,
            )
            for i, (c, d) in enumerate(rows)
        ]
