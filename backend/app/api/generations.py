"""Answers: start one (streamed as Server-Sent Events), read, cancel and open its citations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.database import get_db
from app.core.security import current_user
from app.models import Message
from app.schemas import GenerationCreate
from app.services import generations
from app.services.chat_stream import generate_stream

router = APIRouter(tags=["generations"])


def generation_json(db, g):
    m = db.get(Message, g.assistant_message_id)
    return dict(
        id=g.id,
        generation_id=g.id,
        status=g.status,
        content=m.content if m else "",
        model_id=g.model_id,
        provider=g.provider,
        citations=g.sources,
        sources=g.sources,
        error_code=g.error_code,
    )


@router.post("/conversations/{id}/generations")
def create_generation(
    id: UUID, body: GenerationCreate, request: Request, user=Depends(current_user), db=Depends(get_db)
):
    g, model, replayed = generations.start_generation(db, user, id, body)
    if replayed:  # same request_id sent again: report the original instead of calling the model twice
        return dict(generation_id=g.id, status=g.status)
    return StreamingResponse(
        generate_stream(g.id, model, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/generations/{id}")
def get_generation(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return generation_json(db, generations.owned_generation(db, user.id, id))


@router.post("/generations/{id}/cancel")
def cancel_generation(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    g = generations.cancel(db, user.id, id)
    return {"status": g.status, "generation_id": g.id}


@router.get("/generations/{id}/citations/{citation_id}")
def citation(id: UUID, citation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return generations.citation(db, user.id, id, citation_id)
