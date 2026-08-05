import asyncio
from datetime import date
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.services.signal_engine import compute_signals_for_date


async def run():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT COUNT(*) FROM signals s "
            "JOIN fixtures f ON s.fixture_id = f.id "
            "WHERE f.event_date = '2026-08-04'"
        ))
        print(f"Current signals for Aug 4: {result.scalar()}")

        await db.execute(text(
            "DELETE FROM signals WHERE fixture_id IN "
            "(SELECT id FROM fixtures WHERE event_date = '2026-08-04')"
        ))
        await db.commit()
        print("Deleted existing Aug 4 signals")

    async with AsyncSessionLocal() as db:
        target = date(2026, 8, 4)
        count = await compute_signals_for_date(db, target)
        print(f"Recomputed: {count} signals for {target}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT s.poisson_rule_key, f.league, f.country, s.bayesian_best_odd "
            "FROM signals s JOIN fixtures f ON s.fixture_id = f.id "
            "WHERE f.event_date = '2026-08-04' AND s.market = 'Under 3.5' "
            "ORDER BY s.poisson_rule_key, f.league"
        ))
        rows = result.all()
        print(f"\nUnder 3.5 signals for Aug 4 ({len(rows)} total):")
        for r in rows:
            print(f"  [{r[0]}] {r[2]} | {r[1]} @ {r[3]}")

        result2 = await db.execute(text(
            "SELECT s.market, s.poisson_rule_key, COUNT(*) "
            "FROM signals s JOIN fixtures f ON s.fixture_id = f.id "
            "WHERE f.event_date = '2026-08-04' "
            "GROUP BY s.market, s.poisson_rule_key ORDER BY s.market"
        ))
        print("\nAll Aug 4 signals by market/rule:")
        for r in result2.all():
            print(f"  {r[0]} | {r[1]} | count={r[2]}")


asyncio.run(run())
