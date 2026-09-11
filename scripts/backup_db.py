#!/usr/bin/env python
"""Database backup script — writes a compressed pg_dump to BACKUP_DIR.

Usage::

    python scripts/backup_db.py

Reads the same DATABASE_URL and BACKUP_DIR / BACKUP_KEEP_COUNT from the .env
file (via pydantic-settings) so no extra configuration is needed.

The script:
1. Runs ``pg_dump`` against the configured database.
2. Compresses the dump with gzip.
3. Names the file ``qwantej_YYYYMMDD_HHMMSS.sql.gz``.
4. Deletes the oldest dumps beyond BACKUP_KEEP_COUNT (default 7).

Intended for scheduled invocation (cron, APScheduler, Fly.io cron).  Never
targets a production database without explicit confirmation (see DEVELOPMENT.md
§3 — never modify production data directly).
"""

from __future__ import annotations

import gzip
import logging
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)


def _parse_db_url(database_url: str) -> dict[str, str]:
    """Extract connection components from a SQLAlchemy DSN."""
    # Strip driver prefix: postgresql+psycopg://... → postgresql://...
    url = database_url.split("+")[0] + "://" + database_url.split("://", 1)[1]
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/qwantej").lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def run_backup(
    *,
    database_url: str,
    backup_dir: Path,
    keep_count: int = 7,
    pg_dump_bin: str = "pg_dump",
) -> Path:
    """Run a pg_dump backup and return the path to the compressed file.

    Parameters
    ----------
    database_url:
        Full SQLAlchemy-style DSN.
    backup_dir:
        Directory to write backups.  Created if it does not exist.
    keep_count:
        Number of most-recent backups to retain; older files are deleted.
    pg_dump_bin:
        Path to the pg_dump executable.
    """
    if keep_count < 1:
        raise ValueError(f"keep_count must be >= 1, got {keep_count}")

    backup_dir.mkdir(parents=True, exist_ok=True)

    conn = _parse_db_url(database_url)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S_%f")
    out_path = backup_dir / f"qwantej_{timestamp}.sql.gz"

    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = conn["password"]

    cmd = [
        pg_dump_bin,
        "-h", conn["host"],
        "-p", conn["port"],
        "-U", conn["user"],
        "-d", conn["dbname"],
        "--no-password",
        "--format=plain",
        "--no-owner",
        "--no-acl",
    ]

    log.info("backup_db: running pg_dump to %s", out_path)
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {stderr}")

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=backup_dir
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with gzip.open(temp_path, "wb") as gz:
            gz.write(result.stdout)
        verify_backup(temp_path)
        temp_path.replace(out_path)
    finally:
        temp_path.unlink(missing_ok=True)

    size_kb = out_path.stat().st_size // 1024
    log.info("backup_db: wrote %s (%d KB)", out_path.name, size_kb)

    _prune_old_backups(backup_dir, keep_count=keep_count)
    return out_path


def verify_backup(path: Path) -> None:
    """Verify a readable, non-empty plain-SQL gzip dump.

    This catches truncated gzip files and empty/non-dump output before the
    backup is promoted or retained. Restore drills must use a disposable DB.
    """

    try:
        with gzip.open(path, "rb") as gz:
            prefix = gz.read(256)
    except (OSError, EOFError) as exc:
        raise RuntimeError(f"backup verification failed for {path.name}") from exc
    if not prefix or b"PostgreSQL database dump" not in prefix:
        raise RuntimeError(f"backup verification failed for {path.name}: invalid SQL dump")


def _prune_old_backups(backup_dir: Path, *, keep_count: int) -> None:
    """Delete oldest ``qwantej_*.sql.gz`` files beyond *keep_count*.

    *keep_count* must be >= 1.  Python's ``seq[:-0]`` resolves to ``seq[:0]``
    (empty), so zero silently keeps everything — we reject it explicitly rather
    than producing surprising behaviour.
    """
    if keep_count < 1:
        raise ValueError(f"keep_count must be >= 1, got {keep_count}")
    dumps = sorted(backup_dir.glob("qwantej_*.sql.gz"))
    to_delete = dumps[:-keep_count] if len(dumps) > keep_count else []
    for old in to_delete:
        old.unlink()
        log.info("backup_db: pruned %s", old.name)


def main() -> None:
    import sys

    # Add repo root to path so backend.core is importable
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        from backend.core.config import get_settings
        settings = get_settings()
        database_url = settings.database_url
        backup_dir = Path(settings.backup_dir)
        keep_count = settings.backup_keep_count
    except Exception as exc:
        log.error("backup_db: could not load settings: %s", exc)
        sys.exit(1)

    try:
        out = run_backup(
            database_url=database_url,
            backup_dir=backup_dir,
            keep_count=keep_count,
        )
        print(f"Backup complete: {out}")
    except Exception as exc:
        log.error("backup_db: failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
