"""Sync Jul 28 fixtures (to get scores) then settle all pending bets."""
import asyncio, json
from datetime import date
from app.core.database import AsyncSessionLocal, init_db
# Import all models so SQLAlchemy metadata is fully populated
import app.models.user
import app.models.fixture
import app.models.signal
import app.models.odds
import app.models.bet
import app.models.backtest
import app.models.ingestion
import app.models.loss_analysis
import app.models.learning_proposal
from sqlalchemy import text

async def run():
    await init_db()

    # Step 1: Sync Jul 28 to pull scores
    print("=== Syncing 2026-07-28 fixtures ===")
    from app.services.ingestion import sync_date
    async with AsyncSessionLocal() as db:
        result = await sync_date(db, run_date=date(2026, 7, 28), force=True)
        print("Sync result:", json.dumps(result, default=str))

    # Step 2: Settle
    print("\n=== Running settlement ===")
    from app.services.settlement import settle_bets_for_date
    async with AsyncSessionLocal() as db:
        result = await settle_bets_for_date(db, run_date=None)
        await db.commit()
        print("Settlement result:", json.dumps(result, default=str))

    # Step 3: Show what's now pending vs settled
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT tb.id, tb.result_status, tb.market_type, tb.odds, tb.stake, tb.profit_loss,
                   tb.league, f.home_team, f.away_team, f.home_score, f.away_score, f.status
            FROM tracked_bets tb
            LEFT JOIN fixtures f ON tb.fixture_id = f.id
            WHERE tb.id IN (975, 976, 977)
            ORDER BY tb.id
        """))
        rows = [dict(r) for r in r.mappings().all()]
        print("\n=== Final status of pending bets ===")
        print(json.dumps(rows, default=str))

asyncio.run(run())
