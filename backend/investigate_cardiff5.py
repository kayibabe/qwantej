if __name__ == "__main__":
    import asyncio
    from datetime import date
    from app.core.database import AsyncSessionLocal, init_db
    from app.services.form_service import get_team_form_lambdas
    from app.services.advanced_models_service import AdvancedModelsService

    async def main():
        await init_db()

        async with AsyncSessionLocal() as db:
            form = await get_team_form_lambdas(
                db=db,
                home_team="Cardiff MET",
                away_team="Holywell",
                before_date=date(2026, 8, 1),
            )
            print(f"Form lambdas: {form}")
            fallback_lh = form.get("lambda_h") or 1.35
            fallback_la = form.get("lambda_a") or 1.10
            print(f"Effective fallbacks: lh={fallback_lh}, la={fallback_la}")

            adv = AdvancedModelsService(db)
            try:
                await adv.load()
                print(f"\nAdvanced models loaded OK")
            except Exception as e:
                print(f"\nAdvanced models load FAILED: {e}")

            fitted = adv.zinb_is_fitted("Premier League")
            print(f"ZINB fitted for 'Premier League': {fitted}")

            zinb_lh, zinb_la = adv.zinb_predict(
                league="Premier League",
                home_team="Cardiff MET",
                away_team="Holywell",
                fallback_lh=fallback_lh,
                fallback_la=fallback_la,
            )
            print(f"zinb_predict: lh={zinb_lh}, la={zinb_la}")

    asyncio.run(main())
