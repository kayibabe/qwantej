if __name__ == "__main__":
    import pickle, pathlib

    cache_path = pathlib.Path(".cache/advanced_models/2026-08-01_42554-43375.pkl")
    with open(cache_path, "rb") as f:
        obj = pickle.load(f)

    from app.services.advanced_models_service import _team_hash
    cardiff_hash = _team_hash("Cardiff MET")
    holywell_hash = _team_hash("Holywell")
    print(f"Cardiff MET hash: {cardiff_hash}")
    print(f"Holywell hash: {holywell_hash}")

    # Get the "premier league" model
    m = obj._zinb_models.get("premier league")
    if m is None:
        print("No 'premier league' model found"); exit()

    print(f"\nModel type: {type(m)}")
    print(f"Model fitted: {m.fitted}")

    # Dump internal state
    for attr in dir(m):
        if attr.startswith("_") and not attr.startswith("__"):
            v = getattr(m, attr, None)
            if v is not None and not callable(v):
                print(f"  {attr}: {type(v).__name__} = {str(v)[:200]}")
