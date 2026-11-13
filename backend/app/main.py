"""FastAPI application: CORS, security headers, one JSON error shape, and the /api/v1 routes."""

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
cfg = settings()
# The interactive API docs are for development only.
docs = cfg.app_env != "production"
app = FastAPI(
    title="Gehihi",
    version="1.0.0",
    docs_url="/api/docs" if docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in cfg.cors_origins.split(",") if x.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    allow_credentials=True,  # the refresh-token cookie on /auth routes
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    """Refuse oversized uploads from the header, before the framework buffers the body."""
    if request.method == "POST" and request.url.path == "/api/v1/documents":
        length = request.headers.get("content-length")
        if not length or not length.isdigit():
            return JSONResponse(dict(code="length_required", message="Content-Length is required"), 411)
        if int(length) > cfg.max_upload_bytes + 1_048_576:  # + multipart overhead
            return JSONResponse(dict(code="too_large", message="File empty or exceeds 10 MiB"), 413)
    return await call_next(request)


# Every error is {code, message, request_id}.
def _error(request, status, code, message, request_id=None):
    request_id = request_id or getattr(request.state, "request_id", None)
    return JSONResponse(dict(code=code, message=message, request_id=request_id), status_code=status)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    """`detail` is a message, or a dict with code/message/request_id (deletions echo their idempotency key)."""
    detail = error.detail if isinstance(error.detail, dict) else dict(message=error.detail)
    return _error(
        request,
        error.status_code,
        detail.get("code", f"http_{error.status_code}"),
        detail.get("message", "Request failed"),
        detail.get("request_id"),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return _error(request, 422, "invalid_request", "Invalid request fields")


@app.exception_handler(Exception)
async def server_error(request, error):
    logging.error(
        "request_failed request_id=%s path=%s", getattr(request.state, "request_id", None), request.url.path, exc_info=error
    )
    return _error(request, 500, "server_error", "Something went wrong. Try again.")


app.include_router(api_router)
