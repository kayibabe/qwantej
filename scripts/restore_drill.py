#!/usr/bin/env python
"""Restore a Qwantej SQL backup into a disposable local database.

The drill is intentionally guarded against production use: the target must be
on loopback, must have a disposable-looking name, and must differ from the
source database. The target is removed after verification unless
``--keep-target`` is supplied for inspection.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.backup_db import _parse_db_url  # noqa: E402

log = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DISPOSABLE_DB_RE = re.compile(r"^(?:qwantej_)?(?:restore|drill)(?:[_-][A-Za-z0-9_-]+)?$")


def _validate_target(source: dict[str, str], target_db: str) -> None:
    """Reject targets that could accidentally refer to a real database."""

    if source["host"].lower() not in _LOCAL_HOSTS:
        raise ValueError("restore drill requires a loopback DATABASE_URL host")
    if target_db == source["dbname"]:
        raise ValueError("restore drill target must differ from the source database")
    if _DISPOSABLE_DB_RE.fullmatch(target_db) is None:
        raise ValueError(
            "restore drill target must be named qwantej_restore*, qwantej_drill*, "
            "restore*, or drill*"
        )


def _restore_environment(conn: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = conn["password"]
    return env


def _admin_connection(conn: dict[str, str]) -> Any:
    import psycopg

    return psycopg.connect(
        host=conn["host"],
        port=int(conn["port"]),
        dbname="postgres",
        user=conn["user"],
        password=conn["password"] or None,
        connect_timeout=10,
    )


def _recreate_target(conn: dict[str, str], target_db: str) -> None:
    from psycopg import sql

    with _admin_connection(conn) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (target_db,),
            )
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target_db)))
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))


def _restore_sql(backup_path: Path, conn: dict[str, str], target_db: str, psql_bin: str) -> None:
    command = [
        psql_bin,
        "--host", conn["host"],
        "--port", conn["port"],
        "--username", conn["user"],
        "--dbname", target_db,
        "--no-password",
        "--set=ON_ERROR_STOP=1",
    ]
    with gzip.open(backup_path, "rb") as dump:
        sql_dump = dump.read()
        result = subprocess.run(  # noqa: S603
            command,
            input=sql_dump,
            capture_output=True,
            env=_restore_environment(conn),
            check=False,
        )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"psql restore failed (exit {result.returncode}): {detail}")


def _verify_target(conn: dict[str, str], target_db: str) -> dict[str, str]:
    import psycopg

    with psycopg.connect(
        host=conn["host"],
        port=int(conn["port"]),
        dbname=target_db,
        user=conn["user"],
        password=conn["password"] or None,
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            alembic_row = cursor.fetchone()
            if alembic_row is None:
                raise RuntimeError("restored database has no Alembic version")
            alembic_head = str(alembic_row[0])
            cursor.execute("SELECT to_regclass('public.fixtures')")
            fixtures_row = cursor.fetchone()
            if fixtures_row is None:
                raise RuntimeError("could not verify restored fixtures table")
            fixtures_table = str(fixtures_row[0])
            cursor.execute("SELECT COUNT(*) FROM fixtures")
            count_row = cursor.fetchone()
            if count_row is None:
                raise RuntimeError("could not verify restored fixture count")
            fixture_count = str(count_row[0])
    return {
        "alembic_head": alembic_head,
        "fixtures_table": fixtures_table,
        "fixture_count": fixture_count,
    }


def run_restore_drill(
    *,
    backup_path: Path,
    database_url: str,
    target_db: str = "qwantej_restore_drill",
    psql_bin: str = "psql",
    keep_target: bool = False,
) -> dict[str, str]:
    """Restore and verify *backup_path* in a disposable loopback database."""

    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    source = _parse_db_url(database_url)
    _validate_target(source, target_db)
    _recreate_target(source, target_db)
    try:
        _restore_sql(backup_path, source, target_db, psql_bin)
        result = _verify_target(source, target_db)
        log.info("restore drill verified %s: %s", target_db, result)
        return result
    finally:
        if not keep_target:
            _drop_target(source, target_db)


def _drop_target(conn: dict[str, str], target_db: str) -> None:
    from psycopg import sql

    with _admin_connection(conn) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (target_db,),
            )
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target_db)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True, help="gzip SQL backup to restore")
    parser.add_argument("--database-url", help="loopback source DATABASE_URL")
    parser.add_argument("--target-db", default="qwantej_restore_drill")
    parser.add_argument("--psql-bin", default="psql")
    parser.add_argument("--keep-target", action="store_true")
    args = parser.parse_args()

    from backend.core.config import get_settings

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    result = run_restore_drill(
        backup_path=args.backup,
        database_url=args.database_url or settings.database_url,
        target_db=args.target_db,
        psql_bin=args.psql_bin,
        keep_target=args.keep_target,
    )
    print(f"Restore drill complete: {result}")


if __name__ == "__main__":
    main()
