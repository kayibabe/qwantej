import asyncio, json
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def run():
    async with AsyncSessionLocal() as db:
        # Overall
        r = await db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result_status='Lost' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result_status='Pending' THEN 1 ELSE 0 END) as pending,
                SUM(stake) as total_staked,
                SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                         WHEN result_status='Lost' THEN -stake ELSE 0 END) as pnl,
                AVG(CASE WHEN result_status IN ('Won','Lost') THEN odds END) as avg_odds
            FROM tracked_bets
            WHERE result_status IN ('Won','Lost','Pending')
        """))
        overall = dict(r.mappings().one())
        settled_staked = sum([overall['total_staked'] or 0]) - (overall['pending'] or 0)
        print('OVERALL:', json.dumps(overall, default=str))

        # By market
        r2 = await db.execute(text("""
            SELECT market_type,
                COUNT(*) as n,
                SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) as wins,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) as wr,
                SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                         WHEN result_status='Lost' THEN -stake ELSE 0 END) as pnl,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                                     WHEN result_status='Lost' THEN -stake ELSE 0 END)
                           /NULLIF(SUM(CASE WHEN result_status IN ('Won','Lost') THEN stake ELSE 0 END),0),1) as roi,
                ROUND(AVG(CASE WHEN result_status IN ('Won','Lost') THEN odds END),3) as avg_odds
            FROM tracked_bets
            WHERE result_status IN ('Won','Lost')
            GROUP BY market_type
            ORDER BY n DESC
        """))
        markets = [dict(r) for r in r2.mappings().all()]
        print('MARKETS:', json.dumps(markets, default=str))

        # By league top 25
        r3 = await db.execute(text("""
            SELECT league,
                COUNT(*) as n,
                SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) as wins,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) as wr,
                SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                         WHEN result_status='Lost' THEN -stake ELSE 0 END) as pnl,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                                     WHEN result_status='Lost' THEN -stake ELSE 0 END)
                           /NULLIF(SUM(CASE WHEN result_status IN ('Won','Lost') THEN stake ELSE 0 END),0),1) as roi
            FROM tracked_bets
            WHERE result_status IN ('Won','Lost')
            GROUP BY league
            ORDER BY n DESC
            LIMIT 25
        """))
        leagues = [dict(r) for r in r3.mappings().all()]
        print('LEAGUES:', json.dumps(leagues, default=str))

        # Monthly P&L
        r4 = await db.execute(text("""
            SELECT strftime('%Y-%m', settled_at) as month,
                COUNT(*) as n,
                SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) as wins,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) as wr,
                SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                         WHEN result_status='Lost' THEN -stake ELSE 0 END) as pnl,
                SUM(stake) as staked
            FROM tracked_bets
            WHERE result_status IN ('Won','Lost') AND settled_at IS NOT NULL
            GROUP BY month
            ORDER BY month
        """))
        monthly = [dict(r) for r in r4.mappings().all()]
        print('MONTHLY:', json.dumps(monthly, default=str))

        # Active learning proposals
        r5 = await db.execute(text("""
            SELECT change_type, target, proposed_value, confidence, backtest_note, created_at
            FROM learning_proposals
            WHERE is_active=1
            ORDER BY created_at DESC
            LIMIT 20
        """))
        proposals = [dict(r) for r in r5.mappings().all()]
        print('PROPOSALS:', json.dumps(proposals, default=str))

        # By confidence+agreement
        r6 = await db.execute(text("""
            SELECT source_rule_key,
                COUNT(*) as n,
                SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END) as wins,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) as wr,
                SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                         WHEN result_status='Lost' THEN -stake ELSE 0 END) as pnl,
                ROUND(100.0*SUM(CASE WHEN result_status='Won' THEN (odds-1)*stake
                                     WHEN result_status='Lost' THEN -stake ELSE 0 END)
                           /NULLIF(SUM(CASE WHEN result_status IN ('Won','Lost') THEN stake ELSE 0 END),0),1) as roi
            FROM tracked_bets
            WHERE result_status IN ('Won','Lost') AND source_rule_key IS NOT NULL
            GROUP BY source_rule_key
            ORDER BY n DESC
            LIMIT 20
        """))
        rules = [dict(r) for r in r6.mappings().all()]
        print('RULES:', json.dumps(rules, default=str))

asyncio.run(run())
