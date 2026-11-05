import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


def build_engine_options(worker: bool | None = None) -> dict:
    """Return engine options appropriate to the current process type.

    Celery's prefork workers execute each task with its own asyncio.run() loop.
    A pooled asyncpg connection cannot safely cross those loops, so workers use
    NullPool. The API process keeps a bounded queue pool instead of opening a
    fresh Postgres connection for every request.
    """
    if worker is None:
        worker = os.getenv("CELERY_WORKER") == "1"
    if worker:
        return {"pool_pre_ping": True, "poolclass": NullPool}
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }


engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    **build_engine_options(),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
