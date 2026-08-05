if __name__ == "__main__":
    import asyncio
    from datetime import date
    from app.core.database import AsyncSessionLocal, init_db
    from app.services.form_service import get_team_form_lambdas, _fetch_team_goals
    from app.core.config import POISSON_RULES

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            before = date(2026, 8, 1)
            n = int(POISSON_RULES["rolling_form_games"])
            min_g = int(POISSON_RULES["form_min_games"])

            hg, hc = await _fetch_team_goals(db, "Cardiff MET", before, n)
            ag, ac = await _fetch_team_goals(db, "Holywell", before, n)
            print(f"Cardiff MET goals  (n={n}, need>={min_g}): {hg}")
            print(f"Cardiff MET conced:                        {hc}")
            print(f"Holywell    goals  (n={n}, need>={min_g}): {ag}")
            print(f"Holywell    conced:                        {ac}")

            form = await get_team_form_lambdas(
                db=db, home_team="Cardiff MET", away_team="Holywell", before_date=before
            )
            print(f"\nform_lambdas: {form}")

    asyncio.run(main())
