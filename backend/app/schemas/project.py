"""Projects and their documents."""

from pydantic import Field

from app.schemas.common import DisplayName, Strict, Text


class ProjectBody(Strict):
    name: Text = Field(min_length=1, max_length=120)


class DocumentUpdate(Strict):
    name: DisplayName = Field(min_length=1, max_length=255)
