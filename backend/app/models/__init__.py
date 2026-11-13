"""SQLAlchemy tables, one module per area. Import from here: `from app.models import User`.

Importing this package registers every table on `Base.metadata`.
"""

from app.models.chat import Conversation, Generation, Message
from app.models.common import now, uid
from app.models.document import Chunk, Document
from app.models.jobs import Deletion, Job
from app.models.project import Project
from app.models.usage import Usage
from app.models.user import LoginSession, User, UserKey

__all__ = [
    "Chunk",
    "Conversation",
    "Deletion",
    "Document",
    "Generation",
    "Job",
    "LoginSession",
    "Message",
    "Project",
    "Usage",
    "User",
    "UserKey",
    "now",
    "uid",
]
