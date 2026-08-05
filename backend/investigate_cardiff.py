if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, func, text
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.signal import Signal
    from app.models.fixture import Fixture
    from app.models.odds import MarketSnapshot

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            # Find the fixture
            fix = (await db.execute(
                select(Fixture).where(Fixture.home_team.like("%Cardiff MET%"))
            )).scalars().first()

            if not fix:
                print("Fixture not found")
                return

            print("=== FIXTURE ===")
            for col in ["id", "home_team", "away_team", "league", "country", "kickoff_at",
                        "status", "tier", "home_score", "away_score"]:
                print(f"  {col}: {getattr(fix, col, '?')}")

            # Find all signals for this fixture
            sigs = (await db.execute(
                select(Signal).where(Signal.fixture_id == fix.id)
            )).scalars().all()

            print(f"\n=== SIGNALS ({len(sigs)}) ===")
            for s in sigs:
                print(f"  market={s.market}  rule_key={s.poisson_rule_key}  conf={s.dual_confidence}")
                print(f"  home_xg={s.home_xg}  away_xg={s.away_xg}  lambda_total={s.poisson_lambda_total}")
                print(f"  bayesian_home_win_prob={s.bayesian_home_win_prob}  bayesian_away_win_prob={s.bayesian_away_win_prob}")
                print(f"  poisson_home_win_prob={s.poisson_home_win_prob}  poisson_away_win_prob={s.poisson_away_win_prob}")
                print()

            # Find odds snapshots for this fixture
            snaps = (await db.execute(
                select(MarketSnapshot).where(MarketSnapshot.fixture_id == fix.id)
            )).scalars().all()

            print(f"=== MARKET SNAPSHOTS ({len(snaps)}) ===")
            for snap in snaps:
                print(f"  market_type={snap.market_type}  bookmaker={snap.bookmaker}  odds={snap.odds}")

    asyncio.run(main())
