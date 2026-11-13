"""Building blocks shared by the request schemas."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


def _stripped(value: str) -> str:
    if not value.strip():
        raise ValueError("Value cannot be blank")
    return value.strip()


def _display_name(value: str) -> str:
    if "/" in value or "\\" in value:
        raise ValueError("Invalid display name")
    return _stripped(value)


Text = Annotated[str, AfterValidator(_stripped)]  # trimmed, never blank
DisplayName = Annotated[str, AfterValidator(_display_name)]  # Text without path separators


class Strict(BaseModel):
    """Rejects unknown fields, so typos in requests fail loudly."""

    model_config = ConfigDict(extra="forbid")
