"""SQLAlchemy engine/session wiring. Kept separate from backend.core.config
so tests can construct an engine against a different URL (e.g. SQLite or a
throwaway Postgres) without touching application settings.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """The process-wide engine, built from application settings on first use."""
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Provide a transactional session; commits on success, rolls back on
    exception. Pass an explicit `engine` (e.g. a test SQLite engine) to
    bypass the process-wide one entirely. FastAPI dependency wiring should
    wrap this via a thin generator in backend.api.deps once the first
    router needs it."""
    if engine is not None:
        session_factory: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False
        )
    else:
        global _session_factory
        if _session_factory is None:
            _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
        session_factory = _session_factory

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
