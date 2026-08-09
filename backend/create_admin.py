"""One-shot admin user creation/reset. Fully standalone — no app imports.
Set ADMIN_EMAIL and ADMIN_PASSWORD env vars before running."""
import asyncio
import os
import re
from pathlib import Path

# ── Read .env directly so we never depend on the app's settings machinery ──────
_ENV_FILE = Path(__file__).resolve().parent / ".env"
_env: dict[str, str] = {}
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        _env[k.strip()] = v.strip().strip('"').strip("'")

def _get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _env.get(key, default)

DATABASE_URL = _get("DATABASE_URL") or _get("DB_URL")
EMAIL    = os.environ["ADMIN_EMAIL"]
PASSWORD = os.environ["ADMIN_PASSWORD"]

print(f"Connecting to: {re.sub(r':([^:@]+)@', ':***@', DATABASE_URL)}")
print(f"Admin email:   {EMAIL}")

# ── Hash password using bcrypt directly (avoids passlib version skew) ──────────
import bcrypt as _bcrypt

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

# ── Async DB using asyncpg directly ────────────────────────────────────────────
import asyncpg
from urllib.parse import urlparse

def _parse_url(url: str):
    """Parse postgresql+asyncpg://user:pass@host:port/db into asyncpg.connect kwargs."""
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    url = re.sub(r"^postgres://", "postgresql://", url)
    p = urlparse(url)
    return dict(
        host=p.hostname or "localhost",
        port=p.port or 5432,
        user=p.username or "postgres",
        password=p.password or "",
        database=(p.path or "/qwantej").lstrip("/"),
    )

async def _init_tables():
    """Import all models so Base.metadata is populated, then create tables."""
    import app.models.user
    import app.models.fixture
    import app.models.signal
    import app.models.odds
    import app.models.bet
    import app.models.backtest
    import app.models.ingestion
    import app.models.loss_analysis
    import app.models.learning_proposal
    import app.models.historical_fixture
    import app.models.forecast_snapshot
    import app.models.data_source_experiment
    import app.models.calibration_record
    import app.models.elo_rating
    from app.core.database import init_db
    await init_db()
    print("Tables created.")

async def main():
    await _init_tables()
    conn_kwargs = _parse_url(DATABASE_URL)
    conn = await asyncpg.connect(**conn_kwargs)
    try:
        row = await conn.fetchrow(
            "SELECT id, email, is_admin FROM users WHERE email = $1", EMAIL
        )
        hashed = hash_password(PASSWORD)
        if row:
            print(f"User exists: id={row['id']}  is_admin={row['is_admin']}")
            await conn.execute(
                "UPDATE users SET hashed_password=$1, is_admin=true, tier='elite', is_active=true WHERE email=$2",
                hashed, EMAIL,
            )
            print("Password reset and is_admin=true set.")
        else:
            print("User not found — listing all users:")
            rows = await conn.fetch("SELECT email, is_admin FROM users")
            if not rows:
                print("No users — creating admin.")
                await conn.execute(
                    """INSERT INTO users
                         (email, hashed_password, name, tier, is_admin, is_active,
                          subscription_status, timezone, created_at)
                       VALUES ($1,$2,'Cromwell','elite',true,true,'active','Africa/Blantyre',now())""",
                    EMAIL, hashed,
                )
                print("Admin user created.")
            else:
                for r in rows:
                    print(r)
    finally:
        await conn.close()

asyncio.run(main())
