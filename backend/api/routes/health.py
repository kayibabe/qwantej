"""Health-check endpoints: liveness (/health) and readiness (/health/ready)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.api.deps import DbDep
from backend.core.config import get_settings
from backend.services.notifier import TelegramNotifier

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict[str, str]:
    """Always returns 200 while the process is alive."""
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: DbDep) -> dict[str, str | bool]:
    """Returns 200 when required services are reachable.

    Checks:
    - Database (required — 500 if unreachable)
    - Telegram (optional — reported but never fails the check)
    """
    db.execute(text("SELECT 1"))

    settings = get_settings()
    notifier = TelegramNotifier.from_settings(settings)
    telegram_status: str | bool
    if notifier.enabled:
        telegram_status = notifier.ping()
    else:
        telegram_status = "not_configured"

    return {"status": "ok", "db": "ok", "telegram": telegram_status}
