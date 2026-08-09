from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Alembic Config object — gives access to values in alembic.ini
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Base.metadata is populated for autogenerate.
from app.core.database import Base  # noqa: E402
import app.models.fixture                  # noqa: F401
import app.models.signal                   # noqa: F401
import app.models.odds                     # noqa: F401
import app.models.bet                      # noqa: F401
import app.models.backtest                 # noqa: F401
import app.models.ingestion                # noqa: F401
import app.models.loss_analysis            # noqa: F401
import app.models.learning_proposal        # noqa: F401
import app.models.user                     # noqa: F401
# Phase 1A — historical warehouse
import app.models.historical_fixture       # noqa: F401
import app.models.forecast_snapshot        # noqa: F401
import app.models.data_source_experiment   # noqa: F401
# Phase 1B — ensemble engine
import app.models.elo_rating               # noqa: F401
# Phase 1C — calibration learning loop
import app.models.calibration_record       # noqa: F401

target_metadata = Base.metadata


def _get_url() -> str:
    """Read and normalise the database URL for asyncpg + Alembic."""
    from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DB_URL")
        or config.get_main_option("sqlalchemy.url")
    )
    if not url:
        raise RuntimeError(
            "No database URL found. Set DATABASE_URL or DB_URL in the environment."
        )
    # Normalise scheme to postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # Strip sslmode — asyncpg on internal Fly.io doesn't need it
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _get_url()
    connectable = create_async_engine(url, connect_args={"ssl": False})
    async with connectable.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
