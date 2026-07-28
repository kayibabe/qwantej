"""Probe DB structure for retrospective simulation."""
import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # Check signal count
        r = await db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN s.selected_market IS NOT NULL AND s.selected_market != '' THEN 1 ELSE 0 END) as with_market
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
        """))
        row = r.fetchone()
        print(f"Signals Jul 8-27: {row.total} total, {row.with_market} with selected_market")

        # Sample a few signals to understand data
        r2 = await db.execute(text("""
            SELECT s.id, f.event_date, f.home_team, f.away_team, f.league,
                   s.selected_market, s.stake_tier, s.recommended_stake,
                   s.away_xg, s.home_xg, s.ep_x2, s.ep_away_o05,
                   f.home_score, f.away_score
            FROM signals s
            JOIN fixtures f ON f.id = s.fixture_id
            WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
              AND s.selected_market IS NOT NULL AND s.selected_market != ''
            LIMIT 5
        """))
        rows = r2.fetchall()
        print("\nSample signals with selected_market:")
        for r in rows:
            print(f"  {r.event_date} {r.home_team} vs {r.away_team}")
            print(f"    Market: {r.selected_market}, Stake: {r.recommended_stake}, Tier: {r.stake_tier}")
            print(f"    xG: H={r.home_xg:.2f} A={r.away_xg:.2f}, EP_X2={r.ep_x2}, EP_AO05={r.ep_away_o05}")
            print(f"    Score: {r.home_score}-{r.away_score}, League: {r.league}")

        # Check market_snapshots
        r3 = await db.execute(text("PRAGMA table_info(market_snapshots)"))
        cols = r3.fetchall()
        print("\nmarket_snapshots columns:", [c.name for c in cols])

        # Check a sample market_snapshot
        r4 = await db.execute(text("SELECT * FROM market_snapshots LIMIT 1"))
        row4 = r4.fetchone()
        if row4:
            print("Sample market_snapshot:", dict(row4._mapping))

        # Check tracked_bets sample
        r5 = await db.execute(text("""
            SELECT tb.fixture_id, tb.market_type, tb.odds, tb.stake,
                   tb.result_status, tb.profit_loss
            FROM tracked_bets tb
            JOIN fixtures f ON f.id = tb.fixture_id
            WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27'
              AND tb.source_rule_key = 'system_hybrid_b'
            LIMIT 5
        """))
        rows5 = r5.fetchall()
        print("\nSample tracked_bets:")
        for r in rows5:
            print(f"  fixture={r.fixture_id}, market={r.market_type}, odds={r.odds}, stake={r.stake}, status={r.result_status}")

asyncio.run(main())
