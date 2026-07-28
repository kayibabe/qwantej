"""
Settle the backfilled Jul 8-27 bets and print final stats.
Run from backend/:  python settle_backfill.py
"""
import asyncio, sys
from datetime import date, timedelta
sys.path.insert(0, ".")

from sqlalchemy import text
from app.core.database import AsyncSessionLocal, init_db
from app.models.user import User as _User  # registers users table in SA metadata
from app.services.settlement import settle_bets_for_date

START = date(2026, 7, 8)
END   = date(2026, 7, 27)


async def run():
    await init_db()
    d = START
    total = 0
    while d <= END:
        async with AsyncSessionLocal() as db:
            res = await settle_bets_for_date(db, d)
            n = res.get("settled", 0)
            total += n
            if n:
                print(f"  {d}: settled {n}")
        d += timedelta(days=1)
    print(f"\nTotal settled: {total}")

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT result_status, COUNT(*) FROM tracked_bets "
            "WHERE event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND source_rule_key = 'system_hybrid_b' AND user_id IS NULL "
            "GROUP BY result_status"
        ))).all()
        for r in rows:
            print(f"  {r[0]}: {r[1]}")

        stats = (await db.execute(text(
            "SELECT COUNT(*) total, "
            "SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) won, "
            "SUM(CASE WHEN result_status='Lost' THEN 1 ELSE 0 END) lost, "
            "SUM(profit_loss) net_pl, SUM(stake) staked "
            "FROM tracked_bets "
            "WHERE event_date BETWEEN '2026-07-08' AND '2026-07-27' "
            "AND result_status IN ('Won','Lost') "
            "AND source_rule_key = 'system_hybrid_b' AND user_id IS NULL"
        ))).one()
        tot, won, lost, net, staked = stats
        wr  = won / tot * 100 if tot else 0
        roi = net / staked * 100 if staked else 0
        print(f"\n  system_hybrid_b: {tot} settled | {won}W {lost}L | {wr:.1f}% WR | {roi:+.2f}% ROI | net {net:+,.0f} MWK")

asyncio.run(run())
