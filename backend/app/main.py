from __future__ import annotations

# Load .env before any other module reads settings — ensures API keys are in
# os.environ regardless of the working directory uvicorn was launched from.
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(_Path(__file__).resolve().parent.parent / ".env", override=True)

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import jwt
from jwt import PyJWTError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.database import init_db, engine, AsyncSessionLocal
from app.core.migrations import run_migrations
from app.routers import signals, tracker, analytics, backtest, arb as arb_router
from app.routers import leaderboard as leaderboard_router
from app.routers import auth as auth_router
from app.routers import admin as admin_router
from app.routers import payments as payments_router
from app.routers import forecasts as forecasts_router
from app.routers import model_performance as model_performance_router
from app.routers import data_sources as data_sources_router
from app.routers import advisor as advisor_router
from app.scheduler import get_scheduler
import app.models.user  # noqa: F401 — ensures users table is created by init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("Qwantej")
settings = get_settings()


_MAINTENANCE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Qwantej — Maintenance</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }
  .card {
    max-width: 480px;
    width: 100%;
    text-align: center;
  }
  .logo {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #10b981;
    margin-bottom: 2rem;
  }
  .icon {
    font-size: 3.5rem;
    margin-bottom: 1.25rem;
  }
  h1 {
    font-size: 1.5rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 0.75rem;
  }
  p {
    font-size: 1rem;
    color: #94a3b8;
    line-height: 1.6;
    margin-bottom: 0.5rem;
  }
  .badge {
    display: inline-block;
    margin-top: 1.75rem;
    padding: 0.4rem 1rem;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 9999px;
    font-size: 0.8rem;
    color: #64748b;
    letter-spacing: 0.02em;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="logo">Qwantej</div>
    <div class="icon">🔧</div>
    <h1>We'll be back shortly</h1>
    <p>Qwantej is currently undergoing scheduled maintenance.</p>
    <p>We're working to improve your experience and will be live again soon.</p>
    <div class="badge">Scheduled Maintenance</div>
  </div>
</body>
</html>"""


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Returns 503 for all requests when MAINTENANCE_MODE env var is truthy.
    /health and /api/auth/* are always exempt — health keeps Fly.io alive,
    auth lets admins log in during maintenance."""
    _ALWAYS_PASS = ("/health", "/api/auth/")

    async def dispatch(self, request: Request, call_next):
        if os.getenv("MAINTENANCE_MODE", "").lower() in ("1", "true", "yes"):
            path = request.url.path
            if path == "/health" or path.startswith("/api/auth/"):
                return await call_next(request)
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Qwantej is temporarily down for maintenance. Please check back soon."},
                    headers={"Retry-After": "3600"},
                )
            return HTMLResponse(
                content=_MAINTENANCE_HTML,
                status_code=503,
                headers={"Retry-After": "3600"},
            )
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    When API_KEY is configured, /api/* requests must include either:
      - matching X-API-Key, or
      - a valid Authorization: Bearer JWT (same secret as auth).

    When API_KEY is empty (default) the middleware is a no-op — safe for local dev.
    /health is always exempt so load-balancers and startup probes keep working.
    """
    async def dispatch(self, request: Request, call_next):
        # Auth endpoints are always public — JWT handles their own security.
        exempt = (
            request.url.path.startswith("/api/auth/")
            or request.url.path.startswith("/api/admin/")
            or request.url.path.startswith("/api/payments/")
        )
        if settings.api_key and request.url.path.startswith("/api/") and not exempt:
            if request.headers.get("X-API-Key", "") == settings.api_key:
                return await call_next(request)
            auth = request.headers.get("Authorization") or ""
            if auth.startswith("Bearer "):
                token = auth.removeprefix("Bearer ").strip()
                try:
                    jwt.decode(
                        token,
                        settings.jwt_secret,
                        algorithms=[settings.jwt_algorithm],
                    )
                    return await call_next(request)
                except JWTError:
                    pass
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)


async def _cleanup_stale_ingestion_runs() -> int:
    """
    Mark any ingestion run that never finished (no ended_at) as 'error'.
    These are left behind whenever the backend is restarted mid-sync.
    Safe to run at every startup — only touches rows with ended_at IS NULL.
    """
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            UPDATE ingestion_runs
            SET status      = 'error',
                ended_at    = started_at,
                error_message = 'Marked as error on startup cleanup — backend was restarted mid-sync'
            WHERE (status = 'running' OR status IS NULL)
              AND ended_at IS NULL
        """))
        await db.commit()
        return result.rowcount


@asynccontextmanager
async def lifespan(app: FastAPI):
    # init_db creates tables on a fresh Postgres database (create_all).
    # run_migrations adds any new columns to existing tables — it runs every
    # startup, each DDL in its own transaction so one failure doesn't abort the rest.
    await init_db()
    await run_migrations(engine)

    # Housekeeping: recover from any mid-sync backend restarts
    stale = await _cleanup_stale_ingestion_runs()
    if stale:
        logger.info("Startup cleanup: marked %d stale ingestion run(s) as error", stale)

    # One-shot: purge system_auto bets (Poisson-Only / Bayesian-Only picks that bypass
    # the Both-agreement quality gate). These are no longer tracked going forward.
    from sqlalchemy import text as _text
    async with AsyncSessionLocal() as _db:
        _r = await _db.execute(_text(
            "SELECT COUNT(*) FROM tracked_bets WHERE user_id IS NULL AND source_rule_key = 'system_auto'"
        ))
        _n = _r.scalar() or 0
        if _n > 0:
            await _db.execute(_text(
                "DELETE FROM tracked_bets WHERE user_id IS NULL AND source_rule_key = 'system_auto'"
            ))
            await _db.commit()
            logger.info("Startup cleanup: purged %d system_auto bets (Poisson/Bayesian-Only picks)", _n)

    # One-shot: purge all system ZINB Under 3.5 bets from Aug 9–10 2026 where
    # ZINB had no training coverage (Norwegian divisions, Virsliga, Úrvalsdeild,
    # Irish Premier Division). These were pre-CLV-gate signals from data-desert
    # leagues; all settled as losses. Idempotent — rows already deleted are skipped.
    async with AsyncSessionLocal() as _db3:
        from sqlalchemy import text as _t3
        _r3 = await _db3.execute(_t3(
            "DELETE FROM tracked_bets "
            "WHERE user_id IS NULL "
            "AND source_rule_key = 'system_zinb_goals' "
            "AND market_type = 'Under 3.5' "
            "AND event_date IN ('2026-08-09', '2026-08-10')"
        ))
        if _r3.rowcount:
            await _db3.commit()
            logger.info(
                "Startup cleanup: purged %d ZINB Under 3.5 bets from Aug 9–10 (pre-CLV-gate data-desert losses)",
                _r3.rowcount,
            )

    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Qwantej starting up — scheduler running %d jobs", len(scheduler.get_jobs()))

    # Run the startup sync (catch-up settlement + today's ingestion + signal compute)
    # in the background so it never blocks app startup or health checks. startup_sync
    # self-guards on SKIP_STARTUP_SYNC. It was defined but never wired in, so the app
    # only synced at scheduled cron times and never refreshed "today" on boot — which
    # left the signals/tracker empty after a restart until the next scheduled sync.
    import asyncio as _asyncio
    _force_today = os.getenv("RUN_FORCE_SYNC_TODAY", "").lower() in ("1", "true", "yes")

    # Normal boot: run the startup sync. Skipped when a forced re-sync is requested,
    # so the two don't write to SQLite concurrently (which caused "database is locked").
    if not _force_today:
        from app.scheduler import startup_sync as _startup_sync
        _asyncio.create_task(_startup_sync())

    # One-shot forced re-sync for today, gated by env flag. Bypasses the sync
    # cooldown/cache to re-pull fixtures + odds from the live API and recompute
    # signals. Set RUN_FORCE_SYNC_TODAY=true, deploy/restart, then unset.
    # Runs alone (startup_sync skipped above) to avoid concurrent SQLite writes.
    if _force_today:
        logger.info("RUN_FORCE_SYNC_TODAY set — forcing fresh sync+compute for today")

        async def _force_sync_today():
            from app.core.database import AsyncSessionLocal as _S
            from app.services import ingestion as _ing
            from app.services.ensemble_service import compute_snapshots_for_date as _csfd
            from datetime import date as _d
            async with _S() as _db:
                try:
                    run = await _ing.sync_date(_db, _d.today(), force=True)
                    logger.info("FORCE sync: status=%s fixtures=%s", run.status, run.fixtures_pulled)
                    count = await _csfd(_db, _d.today())
                    await _db.commit()
                    logger.info("FORCE compute: %d snapshots for today", count)
                except Exception:
                    logger.exception("FORCE sync+compute failed")

        _asyncio.create_task(_force_sync_today())

    yield
    scheduler.shutdown(wait=False)
    logger.info("Qwantej shut down.")


app = FastAPI(title="Qwantej", version="1.0.0", lifespan=lifespan)

# Order matters: CORS first so preflight OPTIONS requests are handled before auth check.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(MaintenanceModeMiddleware)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(payments_router.router)
app.include_router(signals.router)
app.include_router(tracker.router)
app.include_router(analytics.router)
app.include_router(backtest.router)
app.include_router(arb_router.router)
app.include_router(leaderboard_router.router)
app.include_router(forecasts_router.router)
app.include_router(model_performance_router.router)
app.include_router(data_sources_router.router)
app.include_router(advisor_router.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# Serve the React SPA when the frontend build is present (production Docker image).
# Registered LAST so it never shadows any /api/* or /health route above.
_frontend_dist = _Path(__file__).resolve().parent.parent / "frontend_dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    _assets = _frontend_dist / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static_assets")

    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_frontend_dist / "index.html"))
