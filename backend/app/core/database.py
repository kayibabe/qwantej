from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def _clean_db_url(url: str) -> str:
    """Strip query params that asyncpg doesn't understand (e.g. sslmode=disable).
    Internal Fly.io connections (.flycast / .internal) don't need SSL at all."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


engine = create_async_engine(
    _clean_db_url(settings.db_url),
    echo=False,
    connect_args={"ssl": False},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
