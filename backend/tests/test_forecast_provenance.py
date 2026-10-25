from app.services.forecast_provenance import forecast_build_id


def test_forecast_build_id_is_stable_and_content_addressed():
    first = forecast_build_id()
    second = forecast_build_id()

    assert first == second
    assert first.startswith("qwantej-scorer-sha256-v1:")
    assert len(first.rsplit(":", 1)[1]) == 64
