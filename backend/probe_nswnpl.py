"""Check NSW NPL and Queensland Premier League impact on simulation."""
import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # Find all signals for NSW NPL / Queensland Premier League in the window
        r = await db.execute(text("""
            SELECT
                f.event_date, f.home_team, f.away_team, f.league, f.country,
                f.home_score, f.away_score,
                s.selected_market, s.ep_x2, s.ep_away_o05
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
              AND (
                LOWER(f.league) LIKE '%new south wales npl%'
                OR LOWER(f.league) LIKE '%nsw npl%'
                OR LOWER(f.league) LIKE '%queensland premier%'
              )
              AND f.home_score IS NOT NULL
            ORDER BY f.event_date
        """))
        rows = r.fetchall()
        print(f"NSW NPL / Qld Premier signals: {len(rows)}")
        for r in rows:
            print(f"  {r.event_date} {r.home_team} vs {r.away_team}")
            print(f"    League: {r.league} | Score: {r.home_score}-{r.away_score}")
            print(f"    Market: {r.selected_market}, ep_x2={r.ep_x2}, ep_ao05={r.ep_away_o05}")

asyncio.run(main())
