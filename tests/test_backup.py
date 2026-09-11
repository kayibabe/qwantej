"""Tests for scripts/backup_db.py — pruning and validation logic."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backup_db import (  # noqa: E402
    _prune_old_backups,
    _server_major_version,
    run_backup,
    verify_backup,
)

# ---------------------------------------------------------------------------
# _prune_old_backups — validation
# ---------------------------------------------------------------------------

def test_prune_rejects_zero_keep_count(tmp_path):
    """keep_count=0 must raise ValueError — dumps[:-0] == [] silently in Python."""
    with pytest.raises(ValueError, match="keep_count must be >= 1"):
        _prune_old_backups(tmp_path, keep_count=0)


def test_prune_rejects_negative_keep_count(tmp_path):
    with pytest.raises(ValueError, match="keep_count must be >= 1"):
        _prune_old_backups(tmp_path, keep_count=-1)


def test_server_major_version_parsing():
    assert _server_major_version("160011") == 16
    assert _server_major_version(150005) == 15
    with pytest.raises(RuntimeError, match="parse PostgreSQL server version"):
        _server_major_version("unknown")


def test_prune_deletes_oldest_files(tmp_path):
    """Keep the N most recent files; delete the rest."""
    names = [f"qwantej_2026090{i}_120000.sql.gz" for i in range(1, 6)]
    for name in names:
        f = tmp_path / name
        f.write_bytes(b"")

    _prune_old_backups(tmp_path, keep_count=3)

    remaining = sorted(p.name for p in tmp_path.glob("qwantej_*.sql.gz"))
    assert remaining == names[-3:]


def test_prune_keeps_all_when_under_limit(tmp_path):
    """When fewer files exist than keep_count, nothing is deleted."""
    for i in range(3):
        (tmp_path / f"qwantej_2026090{i}_120000.sql.gz").write_bytes(b"")

    _prune_old_backups(tmp_path, keep_count=7)

    assert len(list(tmp_path.glob("qwantej_*.sql.gz"))) == 3


# ---------------------------------------------------------------------------
# run_backup — keep_count validation at entry point
# ---------------------------------------------------------------------------

def test_run_backup_rejects_zero_keep_count(tmp_path):
    with pytest.raises(ValueError, match="keep_count must be >= 1"):
        run_backup(
            database_url="postgresql+psycopg://u:p@localhost:5433/db",
            backup_dir=tmp_path,
            keep_count=0,
        )


def test_verify_backup_rejects_invalid_gzip(tmp_path):
    path = tmp_path / "qwantej_bad.sql.gz"
    path.write_bytes(b"not gzip")
    with pytest.raises(RuntimeError, match="verification failed"):
        verify_backup(path)


def test_verify_backup_requires_postgres_dump_header(tmp_path):
    import gzip

    path = tmp_path / "qwantej_bad.sql.gz"
    with gzip.open(path, "wb") as gz:
        gz.write(b"SELECT 1;")
    with pytest.raises(RuntimeError, match="invalid SQL dump"):
        verify_backup(path)


def test_run_backup_promotes_only_verified_dump(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr("scripts.backup_db._validate_pg_dump_compatibility", lambda *args: None)
    monkeypatch.setattr(
        "scripts.backup_db.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, b"-- PostgreSQL database dump\nCREATE TABLE demo;\n", b""
        ),
    )
    out = run_backup(
        database_url="postgresql+psycopg://u:p@localhost:5433/db",
        backup_dir=tmp_path,
        keep_count=1,
        pg_dump_bin="pg_dump",
    )
    assert out.exists()
    verify_backup(out)
    assert not list(tmp_path.glob("*.tmp"))


def test_run_backup_rejects_unverified_dump_without_promoting(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr("scripts.backup_db._validate_pg_dump_compatibility", lambda *args: None)
    monkeypatch.setattr(
        "scripts.backup_db.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    with pytest.raises(RuntimeError, match="verification failed"):
        run_backup(
            database_url="postgresql+psycopg://u:p@localhost:5433/db",
            backup_dir=tmp_path,
            keep_count=1,
        )
    assert not list(tmp_path.glob("qwantej_*.sql.gz"))
