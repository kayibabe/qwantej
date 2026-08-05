if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.signal import Signal
    from app.models.fixture import Fixture
    from app.models.odds import MarketSnapshot
    from datetime import date

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            # Find the signal with the anomalous home_xg
            sig_row = (await db.execute(
                select(Signal, Fixture)
                .join(Fixture, Signal.fixture_id == Fixture.id)
                .where(Signal.home_xg > 10)
                .where(func.date(Fixture.kickoff_at) == date(2026, 8, 1))
            )).first()

            if not sig_row:
                print("No anomalous signal found for today")
                # Search all dates
                sig_row = (await db.execute(
                    select(Signal, Fixture)
                    .join(Fixture, Signal.fixture_id == Fixture.id)
                    .where(Signal.home_xg > 10)
                    .order_by(Fixture.kickoff_at.desc())
                )).first()
                if not sig_row:
                    print("No anomalous signal found at all"); return

            sig, fix = sig_row

            print("=== FIXTURE ===")
            for col in ["id", "home_team", "away_team", "league", "country", "kickoff_at", "status", "tier"]:
                print(f"  {col}: {getattr(fix, col)}")

            print("\n=== SIGNAL ===")
            for col in ["market", "poisson_rule_key", "dual_confidence", "stake_tier",
                        "home_xg", "away_xg", "poisson_lambda_total",
                        "bayesian_home_win_prob", "bayesian_draw_prob", "bayesian_away_win_prob",
                        "poisson_home_win_prob", "poisson_draw_prob", "poisson_away_win_prob",
                        "bayesian_best_odd", "bayesian_bookmaker"]:
                print(f"  {col}: {getattr(sig, col)}")

            # Check market snapshots for this fixture
            snaps = (await db.execute(
                select(MarketSnapshot).where(MarketSnapshot.fixture_id == fix.id)
            )).scalars().all()

            print(f"\n=== MARKET SNAPSHOTS ({len(snaps)}) ===")
            for snap in snaps[:20]:
                print(f"  market_type={snap.market_type}  bookmaker={snap.bookmaker}")
                print(f"  odds={snap.odds}")

            # Also check if there are form/h2h stats or anything that feeds xg
            # Look at the fixture more closely - check all fixture columns
            print("\n=== ALL FIXTURE COLUMNS ===")
            for col in fix.__table__.columns:
                val = getattr(fix, col.name, "N/A")
                if val is not None and str(val) != "None":
                    print(f"  {col.name}: {val}")

    asyncio.run(main())
