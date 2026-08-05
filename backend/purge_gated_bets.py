"""
Purge 8 Under 3.5 tracked bets from 2026-08-04 that are now gated
by the cup/UEFA suppression rules added 2026-08-05.
Uses raw sqlite3 — no app imports required.
Run: python purge_gated_bets.py [--dry-run]
"""
import sqlite3
import sys

DB_PATH = "/data/Qwantej.db"
TARGET_DATE = "2026-08-04"
TARGET_MARKET = "Under 3.5"

MATCH_FRAGMENTS = [
    "myanmar", "laos",
    "maccabi haifa", "ironi tiberias",
    "rodina", "rubin",
    "akron", "rostov",
    "sydkysten", "ish",          # Ishøj — ø may encode differently
    "concepcion", "curico",
    "gilloise", "bodo",
    "shamrock", "egnatia",
]


def is_gated(match_name: str, league: str) -> bool:
    combined = ((match_name or "") + " " + (league or "")).lower()
    return any(frag in combined for frag in MATCH_FRAGMENTS)


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(
        "SELECT id, match_name, league, market_type, result_status "
        "FROM tracked_bets "
        "WHERE event_date = ? AND market_type = ? "
        "ORDER BY match_name",
        (TARGET_DATE, TARGET_MARKET),
    )
    rows = cur.fetchall()

    if not rows:
        print(f"No Under 3.5 bets found for {TARGET_DATE}.")
        con.close()
        return

    print(f"\nAll Under 3.5 bets for {TARGET_DATE}:")
    for r in rows:
        print(f"  [{r['id']}] {r['match_name']} | {r['league']} | {r['result_status']}")

    to_delete = [r for r in rows if is_gated(r["match_name"], r["league"])]
    keep = [r for r in rows if not is_gated(r["match_name"], r["league"])]

    print(f"\nWill DELETE ({len(to_delete)}):")
    for r in to_delete:
        print(f"  [{r['id']}] {r['match_name']} | {r['league']} | {r['result_status']}")

    print(f"\nWill KEEP ({len(keep)}):")
    for r in keep:
        print(f"  [{r['id']}] {r['match_name']} | {r['league']} | {r['result_status']}")

    if not to_delete:
        print("\nNothing to delete.")
        con.close()
        return

    if "--dry-run" in sys.argv:
        print("\n[DRY RUN] No changes made. Re-run without --dry-run to apply.")
        con.close()
        return

    ids = tuple(r["id"] for r in to_delete)
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM tracked_bets WHERE id IN ({placeholders})", ids)
    con.commit()
    print(f"\nDeleted {len(ids)} bets. Done.")
    con.close()


main()
