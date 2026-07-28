"""Check remaining loss patterns: Copa Gaúcha, Russia Second League A, K League 2."""
import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        patterns = [
            ("Copa Gaúcha", "gaúcha"),
            ("Russia Second League A", "division a gold"),
            ("K League 2", "k league 2"),
            ("Ireland First Division", "first division"),
            ("Swiss Challenge League", "challenge league"),
            ("Veikkausliiga", "veikkausliiga"),
            ("NSw NPL test", "new south wales npl"),
        ]
        for label, term in patterns:
            r = await db.execute(text(f"""
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN tb.result_status='Won' THEN 1 ELSE 0 END) as won,
                    SUM(CASE WHEN tb.result_status='Lost' THEN 1 ELSE 0 END) as lost
                FROM tracked_bets tb
                JOIN fixtures f ON f.id = tb.fixture_id
                WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
                  AND LOWER(f.league) LIKE '%{term}%'
                  AND tb.source_rule_key = 'system_hybrid_b'
                  AND tb.result_status IN ('Won','Lost')
            """))
            row = r.fetchone()
            n = (row.won or 0) + (row.lost or 0)
            wr = (row.won or 0) / n * 100 if n else 0
            print(f"  {label:<30} {row.won or 0}W/{row.lost or 0}L  n={n}  WR={wr:.0f}%")

        # Also check all league names for "new south wales"
        r2 = await db.execute(text("""
            SELECT DISTINCT f.league
            FROM fixtures f
            WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
              AND LOWER(f.league) LIKE '%new south wales%'
        """))
        rows = r2.fetchall()
        print(f"\nNSW leagues found:")
        for r in rows:
            print(f"  '{r.league}'")

asyncio.run(main())
