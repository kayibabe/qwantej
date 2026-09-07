"""FastAPI shared dependencies."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.db import session_scope


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session; commits on success, rolls back on exception."""
    with session_scope() as session:
        yield session


# Use this type alias in route signatures to avoid ruff B008.
DbDep = Annotated[Session, Depends(get_db)]
