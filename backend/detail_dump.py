import asyncio, json
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def run():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT tb.id, tb.market_type, tb.odds, tb.stake, tb.result_status, tb.league,
                   f.home_team, f.away_team, f.kickoff_at
            FROM tracked_bets tb
            LEFT JOIN fixtures f ON tb.fixture_id = f.id
            WHERE tb.result_status = 'Pending'
            ORDER BY f.kickoff_at
        """))
        print('PENDING:', json.dumps([dict(r) for r in r.mappings().all()], default=str))

        r2 = await db.execute(text("""
            SELECT tb.id, tb.market_type, tb.odds, tb.stake, tb.league, tb.settled_at,
                   f.home_team, f.away_team, f.home_score, f.away_score
            FROM tracked_bets tb
            LEFT JOIN fixtures f ON tb.fixture_id = f.id
            WHERE tb.result_status = 'Lost'
            ORDER BY tb.settled_at DESC
        """))
        print('LOSSES:', json.dumps([dict(r) for r in r2.mappings().all()], default=str))

asyncio.run(run())
