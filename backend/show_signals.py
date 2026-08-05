if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.signal import Signal
    from app.models.fixture import Fixture
    from datetime import date

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            target = date(2026, 8, 1)
            subq = select(Fixture.id).where(
                func.date(Fixture.kickoff_at) == target
            ).scalar_subquery()

            rows = (await db.execute(
                select(
                    Fixture.home_team, Fixture.away_team, Fixture.league, Fixture.country,
                    Fixture.kickoff_at,
                    Signal.market, Signal.poisson_rule_key, Signal.dual_confidence,
                    Signal.stake_tier, Signal.recommended_stake,
                    Signal.home_xg, Signal.away_xg,
                    Signal.bayesian_best_odd, Signal.bayesian_bookmaker,
                )
                .join(Fixture, Signal.fixture_id == Fixture.id)
                .where(Signal.fixture_id.in_(subq))
                .order_by(Signal.dual_confidence.desc(), Signal.market, Fixture.kickoff_at)
            )).all()

            print(f"{'#':<4} {'Ko':<6} {'Home':<22} {'Away':<22} {'League':<28} {'Market':<12} {'Conf':<10} {'Tier':<8} {'Stake':>8} {'Odds':>6} {'BK':<10} {'hXG':>5} {'aXG':>5} Src")
            print("-" * 172)
            for i, r in enumerate(rows, 1):
                ko = r.kickoff_at.strftime("%H:%M") if r.kickoff_at else "?"
                stake_k = f"K{int(r.recommended_stake//1000)}" if r.recommended_stake else "-"
                odds = f"{r.bayesian_best_odd:.2f}" if r.bayesian_best_odd else "-"
                bk = (r.bayesian_bookmaker or "-")[:10]
                hxg = f"{r.home_xg:.2f}" if r.home_xg else "-"
                axg = f"{r.away_xg:.2f}" if r.away_xg else "-"
                rk = r.poisson_rule_key or ""
                tag = "ZINB" if rk.startswith("zinb_") else "HB"
                print(f"{i:<4} {ko:<6} {r.home_team[:21]:<22} {r.away_team[:21]:<22} {r.league[:27]:<28} {r.market[:11]:<12} {r.dual_confidence[:9]:<10} {r.stake_tier or '':<8} {stake_k:>8} {odds:>6} {bk:<10} {hxg:>5} {axg:>5} [{tag}]")

        print(f"\n{len(rows)} signals total")

    asyncio.run(main())
