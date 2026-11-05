"""Apply or bootstrap the database schema for a Compose deployment.

The historical baseline migration creates the ORM metadata as it exists today,
so replaying the full migration chain against a brand-new database re-adds
tables and columns that the baseline already created. Existing databases still
upgrade normally through Alembic. A genuinely empty database is bootstrapped
from the current metadata and stamped at the current head.
"""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — register every model table


def main() -> None:
    url = settings.database_url.replace("+asyncpg", "+psycopg2", 1)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        config = Config("alembic.ini")
        if not tables:
            Base.metadata.create_all(engine)
            command.stamp(config, "head")
            print("Bootstrapped an empty database at the current Alembic head.")
            return
        if "alembic_version" not in tables:
            raise SystemExit(
                "Refusing to migrate: the database has tables but no alembic_version. "
                "Stamp the correct revision before applying migrations."
            )
        command.upgrade(config, "head")
        print("Applied Alembic migrations to head.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
