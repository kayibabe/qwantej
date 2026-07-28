"""Diagnose why backfilled hybrid_b bets differ from simulation."""
import asyncio, sys
sys.path.insert(0, ".")
from sqlalchemy import text
from app.core.database import AsyncSessionLocal, init_db
from app.models.user import User as _User

async def run():
    await init_db()
    async with AsyncSessionLocal() as db:

        # 1. How many system_hybrid_b bets by market?
        print("=== system_hybrid_b by market ===")
        rows = (await db.execute(text(
            "SELECT market_type, result_status, COUNT(*) n FROM tracked_bets "
            "WHERE event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND source_rule_key='system_hybrid_b' AND user_id IS NULL "
            "GROUP BY market_type, result_status ORDER BY market_type, result_status"
        ))).all()
        for r in rows: print(f"  {r[0]:30s} {r[1]:10s} {r[2]}")

        # 2. Check signals: how many hybrid_b signals have stake_tier != SKIP?
        print("\n=== signals stake_tier distribution ===")
        rows = (await db.execute(text(
            "SELECT s.stake_tier, s.selected_market, COUNT(*) n "
            "FROM signals s JOIN fixtures f ON s.fixture_id = f.id "
            "WHERE f.event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND s.poisson_rule_key = 'hybrid_b' "
            "GROUP BY s.stake_tier, s.selected_market ORDER BY s.stake_tier, s.selected_market"
        ))).all()
        for r in rows: print(f"  stake_tier={r[0]:8s} selected_market={r[1] or 'NULL':20s} n={r[2]}")

        # 3. Check odds distribution of tracked hybrid_b bets
        print("\n=== odds distribution of tracked bets ===")
        rows = (await db.execute(text(
            "SELECT "
            "  SUM(CASE WHEN odds < 1.21 THEN 1 ELSE 0 END) below_121, "
            "  SUM(CASE WHEN odds BETWEEN 1.21 AND 1.50 THEN 1 ELSE 0 END) in_window, "
            "  SUM(CASE WHEN odds > 1.50 THEN 1 ELSE 0 END) above_150 "
            "FROM tracked_bets "
            "WHERE event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND source_rule_key='system_hybrid_b' AND user_id IS NULL"
        ))).one()
        print(f"  <1.21: {rows[0]}  |  1.21-1.50 (window): {rows[1]}  |  >1.50: {rows[2]}")

        # 4. WR for bets inside the odds window only
        print("\n=== WR for bets inside 1.21-1.50 window ===")
        row = (await db.execute(text(
            "SELECT COUNT(*) total, "
            "SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) won, "
            "SUM(CASE WHEN result_status='Lost' THEN 1 ELSE 0 END) lost, "
            "SUM(profit_loss) net, SUM(stake) staked "
            "FROM tracked_bets "
            "WHERE event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND source_rule_key='system_hybrid_b' AND user_id IS NULL "
            "AND result_status IN ('Won','Lost') "
            "AND odds BETWEEN 1.21 AND 1.50"
        ))).one()
        tot, won, lost, net, staked = row
        wr = won/tot*100 if tot else 0
        roi = net/staked*100 if staked else 0
        print(f"  {tot} bets | {won}W {lost}L | {wr:.1f}% WR | {roi:+.2f}% ROI | net {net:+,.0f} MWK")

        # 5. Sample of out-of-window bets (should not exist after fix)
        print("\n=== Sample out-of-window hybrid_b bets (odds > 1.50) ===")
        rows = (await db.execute(text(
            "SELECT tb.odds, tb.market_type, f.league, f.country, "
            "s.stake_tier, s.selected_market, s.ep_x2, s.ep_away_o05 "
            "FROM tracked_bets tb "
            "JOIN fixtures f ON tb.fixture_id = f.id "
            "LEFT JOIN signals s ON s.fixture_id = f.id AND s.market = tb.market_type "
            "WHERE DATE(f.event_date) BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND tb.source_rule_key='system_hybrid_b' AND tb.user_id IS NULL "
            "AND tb.odds > 1.50 LIMIT 10"
        ))).all()
        for r in rows:
            print(f"  odds={r[0]} mkt={r[1]:25s} league={r[2]} stake_tier={r[4]} selected={r[5]}")

asyncio.run(run())
