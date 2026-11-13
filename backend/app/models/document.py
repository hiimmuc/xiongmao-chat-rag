"""Uploaded documents and their embedded text chunks."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Vector, now, uid


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("id", "project_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # Set only for documents uploaded inside a free chat; they never leave that chat.
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    bytes: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(400))
    # uploading -> queued -> processing -> ready | failed; deleting once deleted
    state: Mapped[str] = mapped_column(String(20), default="uploading")
    version: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Chunk(Base):
    __tablename__ = "document_chunks"
    # The composite key pins every chunk to its document's project at the database level.
    __table_args__ = (
        UniqueConstraint("document_id", "version", "ordinal"),
        ForeignKeyConstraint(
            ["document_id", "project_id"], ["documents.id", "documents.project_id"], ondelete="CASCADE"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector())
