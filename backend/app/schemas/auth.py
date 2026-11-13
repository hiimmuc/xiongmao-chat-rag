"""Sign-up, sign-in, password change and account deletion bodies."""

from typing import Annotated

from pydantic import AfterValidator, Field

from app.schemas.common import DisplayName, Strict


def _email(value: str) -> str:
    value = value.strip().lower()
    local, _, domain = value.partition("@")
    if not local or "." not in domain or " " in value or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Enter a valid email address")
    return value


Email = Annotated[str, Field(min_length=3, max_length=254), AfterValidator(_email)]
NewPassword = Annotated[str, Field(min_length=10, max_length=128)]
Password = Annotated[str, Field(min_length=1, max_length=128)]


class SignUp(Strict):
    email: Email
    password: NewPassword
    display_name: DisplayName | None = Field(default=None, max_length=120)


class SignIn(Strict):
    email: Email
    password: Password


class PasswordChange(Strict):
    current_password: Password
    new_password: NewPassword


class AccountDelete(Strict):
    password: Password
