"""Conversations, answers and branches."""

from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import Strict, Text


class ConversationCreate(Strict):
    title: Text = Field(default="New chat", min_length=1, max_length=120)
    project_id: UUID | None = None


class ConversationUpdate(Strict):
    title: Text | None = Field(default=None, min_length=1, max_length=120)
    document_ids: list[UUID] | None = Field(default=None, max_length=100)


class GenerationCreate(Strict):
    """Ask for an answer: either a new `message`, or `retry_of` an earlier answer."""

    request_id: UUID  # idempotency key chosen by the client
    model_id: str = Field(min_length=1, max_length=160)
    message: str | None = Field(default=None, min_length=1, max_length=16000)
    retry_of: UUID | None = None

    @model_validator(mode="after")
    def validate_turn(self):
        if bool(self.retry_of) == (self.message is not None):
            raise ValueError("Provide message or retry_of, not both")
        if self.message is not None and not self.message.strip():
            raise ValueError("Message cannot be blank")
        return self


class BranchBody(Strict):
    message_id: UUID
