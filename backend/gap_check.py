import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def run():
    async with AsyncSessionLocal() as db:
        # Check Sparta Praha and Dinamo Zagreb signals
        r = await db.execute(text("""
            SELECT f.id, f.home_team, f.away_team, f.league,
                   s.market, s.poisson_rule_key, s.bayesian_best_odd,
                   s.dual_confidence
            FROM signals s
            JOIN fixtures f ON s.fixture_id = f.id
            WHERE f.event_date = '2026-08-04'
              AND (f.home_team LIKE '%Sparta%' OR f.home_team LIKE '%Dinamo%'
                   OR f.away_team LIKE '%Lyon%' OR f.away_team LIKE '%Kauno%'
                   OR f.home_team LIKE '%Columbus%' OR f.home_team LIKE '%Auda%')
        """))
        print("Specific fixture signals:")
        for r2 in r.all():
            fid, home, away, league, mkt, rule, odds, conf = r2
            print(f"  {home} vs {away} ({league}): {mkt} | {rule} | @{odds} | {conf}")

        # Check if Hybrid B X2 is in DB for any fixture today
        r3 = await db.execute(text("""
            SELECT f.home_team, f.away_team, f.league, s.market, s.poisson_rule_key, s.bayesian_best_odd
            FROM signals s JOIN fixtures f ON s.fixture_id = f.id
            WHERE f.event_date = '2026-08-04'
              AND (s.market = 'X2 (Draw or Away)' OR s.poisson_rule_key = 'hybrid_b')
        """))
        hb_rows = r3.all()
        print(f"\nHybrid B signals today: {len(hb_rows)}")
        for r2 in hb_rows:
            print(f"  {r2[0]} vs {r2[1]} | {r2[2]} | {r2[3]} | {r2[4]} | @{r2[5]}")

        # Check Dinamo Zagreb snapshots (does it have CS odds?)
        r4 = await db.execute(text("""
            SELECT f.id, f.home_team, f.away_team
            FROM fixtures f
            WHERE f.event_date = '2026-08-04'
              AND f.home_team LIKE '%Dinamo%' AND f.league LIKE '%Champions%'
        """))
        row = r4.fetchone()
        if row:
            fid, home, away = row
            print(f"\nDinamo Zagreb fixture: {fid} — {home} vs {away}")
            r5 = await db.execute(text(
                "SELECT market_type, selection_name, odds FROM market_snapshots "
                "WHERE fixture_id = :fid AND market_type IN ('Correct Score','Goals Over/Under') "
                "AND (selection_name IN ('0:0','1:0','0:1','1:1','Under 3.5','Over 2.5','Over 1.5')) "
                "ORDER BY market_type, selection_name LIMIT 20"
            ), {"fid": fid})
            for r2 in r5.all():
                print(f"  {r2[0]:<25} {r2[1]:<12} @{r2[2]}")

        # Check Columbus Crew
        r6 = await db.execute(text("""
            SELECT f.id, f.home_team, f.away_team
            FROM fixtures f
            WHERE f.event_date = '2026-08-04' AND f.home_team LIKE '%Columbus%'
        """))
        row2 = r6.fetchone()
        if row2:
            fid2, home2, away2 = row2
            print(f"\nColumbus Crew fixture: {fid2} — {home2} vs {away2}")
            r7 = await db.execute(text(
                "SELECT market_type, selection_name, odds FROM market_snapshots "
                "WHERE fixture_id = :fid AND market_type IN ('Correct Score','Goals Over/Under') "
                "AND selection_name IN ('0:0','1:0','0:1','Under 3.5','Under 2.5','Over 2.5','Over 1.5') "
                "ORDER BY market_type, selection_name LIMIT 20"
            ), {"fid": fid2})
            for r2 in r7.all():
                print(f"  {r2[0]:<25} {r2[1]:<12} @{r2[2]}")

asyncio.run(run())
