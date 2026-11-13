"""Projects, the hidden free-chat project and the document scope rule."""

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.models import Conversation, Document, Project, User, now

MAX_PROJECTS = 20


def owned_project(db, user_id, id, kind=None):
    """The active project owned by `user_id` (of `kind` when given); raises 404 otherwise."""
    q = select(Project).where(Project.id == str(id), Project.user_id == user_id, Project.state == "active")
    p = db.scalar(q.where(Project.kind == kind) if kind else q)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def resolve_project(db, user, id=None):
    """The requested project, or the user's oldest one (created on first use)."""
    if id:
        return owned_project(db, user.id, id)
    p = db.scalar(
        select(Project)
        .where(Project.user_id == user.id, Project.state == "active", Project.kind == "project")
        .order_by(Project.created_at, Project.id)
        .limit(1)
    )
    return p or _create_locked(db, user, "My project", "project")


def free_project(db, user):
    """The user's hidden project for chats that belong to no project."""
    p = db.scalar(select(Project).where(Project.user_id == user.id, Project.kind == "free"))
    return p or _create_locked(db, user, "Free chats", "free")


def _create_locked(db, user, name, kind):
    """Create a project once even when two first requests race, by serializing on the user row."""
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    q = select(Project).where(Project.user_id == user.id, Project.state == "active", Project.kind == kind)
    p = db.scalar(q.order_by(Project.created_at, Project.id).limit(1))
    if not p:
        p = Project(user_id=user.id, name=name, kind=kind)
        db.add(p)
    db.commit()
    return p


def in_scope(c):
    """Documents a chat may use: its project's own, or its own session uploads in a free chat."""
    return [
        Document.project_id == c.project_id,
        or_(Document.conversation_id.is_(None), Document.conversation_id == c.id),
    ]


def list_projects(db, user):
    """The user's visible projects with document and chat counts, plus the free-chat project."""
    resolve_project(db, user)
    free = free_project(db, user)
    rows = db.scalars(
        select(Project)
        .where(Project.user_id == user.id, Project.state == "active", Project.kind == "project")
        .order_by(Project.created_at, Project.id)
    ).all()
    counts = {}
    for model, key in ((Document, "documents"), (Conversation, "conversations")):
        for pid, n in db.execute(
            select(model.project_id, func.count())
            .where(model.user_id == user.id, model.state.not_in(("deleting", "deleted")))
            .group_by(model.project_id)
        ):
            counts.setdefault(pid, {})[key] = n
    return free, rows, counts


def create_project(db, user, name):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    n = db.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.user_id == user.id, Project.state == "active", Project.kind == "project")
    )
    if n >= MAX_PROJECTS:
        raise HTTPException(409, "Project limit reached")
    p = Project(user_id=user.id, name=name)
    db.add(p)
    db.commit()
    return p


def rename_project(db, user, id, name):
    p = owned_project(db, user.id, id, "project")
    p.name = name
    p.updated_at = now()
    db.commit()
    return p


def ensure_not_last_project(db, user, id):
    """A user always keeps at least one project."""
    live = db.scalars(
        select(Project.id).where(
            Project.user_id == user.id, Project.state == "active", Project.kind == "project"
        )
    ).all()
    if str(id) in live and len(live) < 2:
        raise HTTPException(409, "Keep at least one project")
