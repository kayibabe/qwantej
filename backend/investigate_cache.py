if __name__ == "__main__":
    import pickle, pathlib

    cache_path = pathlib.Path(".cache/advanced_models/2026-08-01_42554-43375.pkl")
    with open(cache_path, "rb") as f:
        obj = pickle.load(f)

    print(f"Object type: {type(obj)}")
    print(f"Attributes: {[a for a in dir(obj) if not a.startswith(\"__\")]}")

    # Check zinb models
    models = getattr(obj, "_zinb_models", {})
    print(f"\nZINB model leagues ({len(models)}): {list(models.keys())}")

    for league, m in models.items():
        fitted = getattr(m, "fitted", False)
        print(f"  {league!r}: fitted={fitted}")
        if "premier" in league.lower() and fitted:
            print(f"  >>> Checking Premier League ZINB model")
            try:
                from app.services.advanced_models_service import _team_hash
                mu_h, mu_a = m.predict_goals(_team_hash("Cardiff MET"), _team_hash("Holywell"))
                print(f"  predict_goals(CardiffMET, Holywell) = mu_h={mu_h:.4f}, mu_a={mu_a:.4f}")
            except Exception as e:
                print(f"  predict_goals error: {e}")
            # Show raw params
            for attr in ["_params", "params_", "x_", "result_", "_coef"]:
                v = getattr(m, attr, None)
                if v is not None:
                    print(f"  {attr}: {v}")
            # Show teams it knows about
            if hasattr(m, "_team_effects"):
                for team, val in list(m._team_effects.items())[:20]:
                    print(f"    team_effect {team}: {val}")
