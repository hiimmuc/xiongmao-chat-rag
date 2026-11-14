"""Run one answer: gather context, stream the provider's output to the browser as SSE, record the outcome.

Two tasks cooperate: `produce` talks to the provider and fills a queue; `generate_stream` drains the
queue into the HTTP response and stops everything if the browser disconnects.
"""

import asyncio
import json
import logging
import time

from app.core import database
from app.core.config import settings
from app.models import Conversation, Document, Generation, Message, Usage, User, now
from app.services import usage
from app.services.api_keys import api_key_for
from app.services.preferences import STYLES, preferences_for
from app.services.prompts import (
    build_system,
    completed_history,
    drop_unknown_citations,
    fit_history,
    question_message,
)
from app.services.providers import ProviderError, stream_text
from app.services.retrieval import retrieval_query, retrieve

TERMINAL = ("completed", "failed", "cancelled", "interrupted")
HEARTBEAT_SECONDS = 15  # comment line sent while waiting, keeps proxies from closing the stream
ELIGIBILITY_TTL = 0.5  # how often a running answer re-checks that its chat and documents still exist
CHECKPOINT_SECONDS = 1  # how often partial text is saved


def event(kind, data):
    return "event: " + kind + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"




def eligible(db, g):
    """True while the owner, chat, selected documents and run itself are all still live."""
    u = db.get(User, g.user_id)
    c = db.get(Conversation, g.conversation_id)
    if not u or u.state != "active" or not c or c.state != "active" or g.cancel_requested:
        return False
    for item in g.document_versions:
        d = db.get(Document, item["id"])
        if (
            not d
            or d.user_id != g.user_id
            or d.project_id != c.project_id
            or d.conversation_id not in (None, c.id)
            or d.state != "ready"
            or d.version != item["version"]
        ):
            return False
    return True


class Gate:
    """Re-checks eligibility at most once per TTL so a stream does not hit the database per chunk."""

    def __init__(self, id):
        self.id = id
        self.checked = float("-inf")

    def open(self):
        if time.monotonic() - self.checked < ELIGIBILITY_TTL:
            return True
        with database.Session() as db:
            g = db.get(Generation, self.id)
            allowed = bool(g) and eligible(db, g)
        if allowed:
            self.checked = time.monotonic()
        return allowed


def persist(id, content, status=None, error_code=None, guard=False):
    """Save partial or final content and optionally the status.

    With `guard`, raises CancelledError when the run is no longer eligible. A status of
    "stopped" resolves to cancelled or interrupted from the stored cancel flag.
    """
    with database.Session() as db:
        live = db.get(Generation, id)
        if guard and (not live or not eligible(db, live)):
            raise asyncio.CancelledError()
        if not live:
            return
        db.get(Message, live.assistant_message_id).content = content
        if status:
            live.status = (
                ("cancelled" if live.cancel_requested else "interrupted") if status == "stopped" else status
            )
        if error_code:
            live.error_code = error_code
        live.updated_at = now()
        db.commit()








async def generate_stream(id, model, request):
    queue = asyncio.Queue(maxsize=100)
    task = asyncio.create_task(produce(id, model, queue))
    gate = Gate(id)
    try:
        while not await request.is_disconnected():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                item = ": heartbeat\n\n"
            if item is None or not gate.open():
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        with database.Session() as db:
            g = db.get(Generation, id)
            if g and g.status not in TERMINAL:
                g.status = "cancelled" if g.cancel_requested else "interrupted"
                g.updated_at = now()
                db.commit()


async def start_turn(id, queue):
    """Mark the run streaming and return its snapshot, question and history, or None if ineligible."""
    with database.Session() as db:
        g = db.get(Generation, id)
        if not g or not eligible(db, g):
            return None
        question = db.get(Message, g.user_message_id).content
        history = completed_history(db, g)
        g.status = "streaming"
        db.commit()
        await queue.put(
            event(
                "start",
                dict(
                    generation_id=g.id,
                    user_message_id=g.user_message_id,
                    assistant_message_id=g.assistant_message_id,
                    model_id=g.model_id,
                ),
            )
        )
        return g, question, history


async def produce(id, model, queue):
    invocation = metadata = None
    content = ""
    checkpoint = time.monotonic()
    gate = Gate(id)
    try:
        async with asyncio.timeout(settings().generation_timeout):
            turn = await start_turn(id, queue)
            if not turn:
                return
            g, question, history = turn
            sources = await retrieve(retrieval_query(question, history), g)
            with database.Session() as db:
                live = db.get(Generation, id)
                if not live or not eligible(db, live):
                    return
                live.sources = sources
                style = STYLES[preferences_for(db.get(User, g.user_id)).response_style]
                api_key = api_key_for(db, g.user_id, g.provider)
                db.commit()
            await queue.put(event("sources", {"sources": sources}))
            grounded = bool(g.document_versions)
            system = build_system(style, grounded, model)
            final = question_message(question, sources, grounded)
            messages = fit_history(history, system, final, model) + [dict(role="user", content=final)]
            invocation = usage.intent(
                g.user_id,
                g.model_id,
                g.provider,
                "chat",
                conversation_id=g.conversation_id,
                generation_id=g.id,
            )
            usage.dispatch(invocation)
            sequence = 0
            async for kind, value in stream_text(model, messages, system, api_key):
                if not gate.open():
                    raise asyncio.CancelledError()
                if kind == "usage":
                    metadata = value
                    continue
                content += value
                sequence += 1
                if time.monotonic() - checkpoint > CHECKPOINT_SECONDS:
                    persist(id, content, guard=True)
                    checkpoint = time.monotonic()
                await queue.put(event("delta", dict(sequence=sequence, text=value)))
            if not content:
                raise ProviderError("Provider returned no answer")
            usage.finalize(invocation, metadata, "succeeded")
            persist(id, drop_unknown_citations(content, sources), "completed", guard=True)
            with database.Session() as db:
                row = db.get(Usage, invocation)
                counted = usage.brief(row) if row else None
            await queue.put(
                event("done", dict(status="completed", generation_id=id, usage=counted, finish_reason="stop"))
            )
    except asyncio.CancelledError:
        if invocation:
            usage.finalize(invocation, metadata, "cancelled" if metadata else "unknown")
        persist(id, content, "stopped")
        raise
    except Exception as error:
        logging.error("generation_failed generation_id=%s type=%s", id, type(error).__name__)
        if invocation:
            usage.finalize(invocation, metadata, "failed" if metadata else "unknown")
        persist(id, content, "failed", "generation_failed")
        message = (
            str(error)
            if isinstance(error, (ProviderError, ValueError))
            else "Answer failed; retry or check configuration"
        )
        await queue.put(
            event("error", dict(code="generation_failed", message=message, generation_id=id, retryable=True))
        )
    finally:
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
