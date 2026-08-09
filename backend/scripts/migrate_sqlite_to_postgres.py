"""
migrate_sqlite_to_postgres.py — One-shot data migration: SQLite → PostgreSQL

Copies users and tracked_bets (the data worth preserving) from the old SQLite
database into the new PostgreSQL database. Run this once after the Postgres DB
is provisioned and init_db() has created all tables.

Usage (from backend/):
    python scripts/migrate_sqlite_to_postgres.py --sqlite /data/Qwantej.db

The target Postgres URL is read from DATABASE_URL or DB_URL env var.
SQLite path defaults to ./Qwantej.db if --sqlite is not provided.

Tables migrated:
  - users
  - tracked_bets

Tables NOT migrated (will be rebuilt from scratch):
  - fixtures / market_snapshots  — re-ingested from API-Football
  - signals                      — replaced by forecast_snapshots (Phase 1B)
  - loss_analyses                — retired
  - learning_proposals           — retired
  - backtest_results             — retired
  - calibration_snapshots        — rebuilt from new forecast archive
  - telegram_push_log            — not worth migrating (historical push log)
  - ingestion_runs               — not worth migrating
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg


async def get_sqlite_rows(sqlite_path: str, table: str) -> tuple[list[str], list[tuple]]:
    """Return (column_names, rows) for a table from the SQLite DB."""
    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT * FROM {table}") as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return [], []
            col_names = list(rows[0].keys())
            return col_names, [tuple(row) for row in rows]


async def get_pg_columns(conn: asyncpg.Connection, table: str) -> set[str]:
    """Return the set of column names that exist in the Postgres table."""
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
        table,
    )
    return {r["column_name"] for r in rows}


async def upsert_table(
    conn: asyncpg.Connection,
    table: str,
    col_names: list[str],
    rows: list[tuple],
    conflict_col: str = "id",
) -> int:
    if not rows:
        return 0

    # Only keep columns that exist in the Postgres table (schema may differ).
    pg_cols = await get_pg_columns(conn, table)
    keep_idx = [i for i, c in enumerate(col_names) if c in pg_cols]
    kept_cols = [col_names[i] for i in keep_idx]
    kept_rows = [tuple(row[i] for i in keep_idx) for row in rows]

    col_list = ", ".join(f'"{c}"' for c in kept_cols)
    placeholders = ", ".join(f"${i+1}" for i in range(len(kept_cols)))
    update_set = ", ".join(
        f'"{c}" = EXCLUDED."{c}"'
        for c in kept_cols
        if c != conflict_col
    )

    stmt = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f'ON CONFLICT ("{conflict_col}") DO UPDATE SET {update_set}'
    )

    await conn.executemany(stmt, kept_rows)
    return len(kept_rows)


async def migrate(sqlite_path: str, pg_url: str) -> None:
    print(f"Source (SQLite): {sqlite_path}")
    print(f"Target (Postgres): {pg_url[:pg_url.find('@') + 1]}***")

    if not Path(sqlite_path).exists():
        print(f"ERROR: SQLite file not found: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    pg_conn = await asyncpg.connect(pg_url)
    try:
        # ── users ──────────────────────────────────────────────────────────────
        print("\nMigrating users...")
        col_names, rows = await get_sqlite_rows(sqlite_path, "users")
        if rows:
            n = await upsert_table(pg_conn, "users", col_names, rows)
            print(f"  → {n} user(s) migrated")
        else:
            print("  → No users found in SQLite")

        # ── tracked_bets ───────────────────────────────────────────────────────
        # Migrate user-tracked bets (user_id IS NOT NULL) only.
        # System auto-tracked bets (user_id IS NULL) are regenerated from
        # scratch once the new ensemble engine is live.
        print("\nMigrating tracked_bets (user bets only)...")
        col_names, all_rows = await get_sqlite_rows(sqlite_path, "tracked_bets")
        if col_names:
            uid_idx = col_names.index("user_id")
            user_rows = [r for r in all_rows if r[uid_idx] is not None]
            if user_rows:
                n = await upsert_table(pg_conn, "tracked_bets", col_names, user_rows)
                print(f"  → {n} user bet(s) migrated")
            else:
                print("  → No user-tracked bets found in SQLite")
        else:
            print("  → tracked_bets table not found in SQLite")

        # ── Reset sequences so new inserts don't clash ─────────────────────────
        print("\nResetting Postgres sequences...")
        for table in ("users", "tracked_bets"):
            try:
                await pg_conn.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM "{table}"), 1)
                    )
                """)
                print(f"  → {table}.id sequence reset")
            except Exception as exc:
                print(f"  WARNING: could not reset sequence for {table}: {exc}")

        print("\nMigration complete.")

    finally:
        await pg_conn.close()


def _pg_url_from_env() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL", "")
    # asyncpg takes a plain postgresql:// URL, not postgresql+asyncpg://
    return url.replace("postgresql+asyncpg://", "postgresql://")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Qwantej SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default="./Qwantej.db",
        help="Path to the SQLite database file (default: ./Qwantej.db)",
    )
    parser.add_argument(
        "--pg-url",
        default=None,
        help="PostgreSQL connection URL (default: reads DATABASE_URL / DB_URL from env)",
    )
    args = parser.parse_args()

    pg_url = args.pg_url or _pg_url_from_env()
    if not pg_url:
        print(
            "ERROR: No PostgreSQL URL provided. Set DATABASE_URL in the environment "
            "or pass --pg-url.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(migrate(args.sqlite, pg_url))
