import sqlite3

conn = sqlite3.connect("Qwantej.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM market_snapshots")
before = cur.fetchone()[0]
print(f"market_snapshots before: {before:,}")

cur.execute("""
    DELETE FROM market_snapshots
    WHERE fixture_id IN (
        SELECT id FROM fixtures WHERE event_date < date('now', '-30 days')
    )
""")
deleted = cur.rowcount
conn.commit()
print(f"Deleted: {deleted:,} rows")

print("Running VACUUM (this may take a minute)...")
conn.execute("VACUUM")
conn.commit()
conn.close()
print("Done.")
