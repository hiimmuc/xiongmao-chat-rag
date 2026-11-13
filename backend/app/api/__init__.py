"""HTTP routes, one module per resource. Routes stay thin: validate input, call a service, shape JSON.

All routes are mounted under /api/v1 by app/main.py.
"""

from fastapi import APIRouter

from app.api import (
    account,
    auth,
    catalog,
    conversations,
    deletions,
    documents,
    generations,
    health,
    keys,
    preferences,
    projects,
    usage,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    health,
    auth,
    account,
    preferences,
    keys,
    catalog,
    projects,
    conversations,
    generations,
    documents,
    deletions,
    usage,
):
    api_router.include_router(module.router)
