"""/projects: list, create, rename and delete projects."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.api.deletions import deletion_json
from app.core.database import get_db
from app.core.security import current_user
from app.schemas import ProjectBody
from app.services import projects
from app.services.deletions import accept_deletion

router = APIRouter(tags=["projects"])


def project_json(p):
    return dict(id=p.id, name=p.name, created_at=p.created_at, updated_at=p.updated_at)


@router.get("/projects")
def list_projects(user=Depends(current_user), db=Depends(get_db)):
    free, rows, counts = projects.list_projects(db, user)
    return dict(
        free_id=free.id,
        items=[
            dict(
                project_json(p),
                documents=counts.get(p.id, {}).get("documents", 0),
                conversations=counts.get(p.id, {}).get("conversations", 0),
            )
            for p in rows
        ],
    )


@router.post("/projects", status_code=201)
def create_project(body: ProjectBody, user=Depends(current_user), db=Depends(get_db)):
    return project_json(projects.create_project(db, user, body.name))


@router.patch("/projects/{id}")
def rename_project(id: UUID, body: ProjectBody, user=Depends(current_user), db=Depends(get_db)):
    return project_json(projects.rename_project(db, user, id, body.name))


@router.delete("/projects/{id}", status_code=202)
def delete_project(
    id: UUID, idempotency_key: UUID = Header(), user=Depends(current_user), db=Depends(get_db)
):
    projects.ensure_not_last_project(db, user, id)
    return deletion_json(accept_deletion(db, user, "project", id, idempotency_key))
