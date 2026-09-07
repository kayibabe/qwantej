"""Tests for scripts/backup_db.py — pruning and validation logic."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backup_db import _prune_old_backups, run_backup  # noqa: E402

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
