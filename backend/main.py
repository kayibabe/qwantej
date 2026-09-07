"""FastAPI application factory.

Import `app` here to run with uvicorn:

    uvicorn backend.main:app --reload

or in tests via ``from backend.main import app``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import accumulators, health, predictions, settlements
from backend.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

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

    application.include_router(health.router)
    application.include_router(predictions.router)
    application.include_router(settlements.router)
    application.include_router(accumulators.router)

    return application


app = create_app()
