"""Health checks: `live` (process is up) and `ready` (database reachable). No sign-in needed."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core import database

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready():
    with database.Session() as db:
        db.execute(text("SELECT 1 FROM users LIMIT 1"))
    return {"status": "ok"}
