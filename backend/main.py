"""FastAPI application factory.

Import `app` here to run with uvicorn:

    uvicorn backend.main:app --reload

or in tests via ``from backend.main import app``.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    accumulators,
    audit,
    dashboard,
    health,
    models,
    performance,
    predictions,
    settlements,
)
from backend.core.config import get_settings
from backend.core.logging import configure_logging, request_id_ctx
from backend.core.security import normalize_request_id

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    application = FastAPI(
        title="Qwantej API",
        description=(
            "Calibrated probability forecasts, value signals, and settlement "
            "performance for football accumulator intelligence."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment != "production" else [],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Attach a unique request ID to every inbound request.

        Stores the ID in a ContextVar so the logging filter can inject it into
        every log record emitted during this request without the caller having
        to pass it explicitly.
        """
        request_id = normalize_request_id(request.headers.get("X-Request-ID")) or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.info(
                "http request complete method=%s path=%s status=%d elapsed_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "http request failed method=%s path=%s elapsed_ms=%.1f",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    application.include_router(health.router)
    application.include_router(predictions.router)
    application.include_router(settlements.router)
    application.include_router(accumulators.router)
    application.include_router(performance.router)
    application.include_router(models.router)
    application.include_router(audit.router)
    application.include_router(dashboard.router)

    return application


app = create_app()
