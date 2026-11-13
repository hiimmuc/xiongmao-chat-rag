"""Request bodies validated by FastAPI (Pydantic), one module per area."""

from app.schemas.account import (
    KeyBody,
    KeyTest,
    Notifications,
    NotificationsUpdate,
    Preferences,
    PreferencesUpdate,
    ProfileUpdate,
)
from app.schemas.auth import AccountDelete, PasswordChange, SignIn, SignUp
from app.schemas.chat import BranchBody, ConversationCreate, ConversationUpdate, GenerationCreate
from app.schemas.project import DocumentUpdate, ProjectBody

__all__ = [
    "AccountDelete",
    "BranchBody",
    "ConversationCreate",
    "ConversationUpdate",
    "DocumentUpdate",
    "GenerationCreate",
    "KeyBody",
    "KeyTest",
    "Notifications",
    "NotificationsUpdate",
    "PasswordChange",
    "Preferences",
    "PreferencesUpdate",
    "ProfileUpdate",
    "ProjectBody",
    "SignIn",
    "SignUp",
]
