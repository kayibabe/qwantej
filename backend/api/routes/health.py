"""Health-check endpoints: liveness (/health) and readiness (/health/ready)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.api.deps import DbDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict[str, str]:
    """Always returns 200 while the process is alive."""
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: DbDep) -> dict[str, str]:
    """Returns 200 when the database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
