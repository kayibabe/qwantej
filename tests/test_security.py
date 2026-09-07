"""Tests for API key authentication (backend.core.security)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings, get_settings
from backend.main import create_app


def _app_with_key(api_key: str):
    """Return a TestClient backed by an app configured with *api_key*."""
    settings = Settings(api_key=api_key)
    get_settings.cache_clear()

    app = create_app()

    # Override the settings singleton so the app uses our key.
    from backend import core
    original = core.config.get_settings
    core.config.get_settings = lambda: settings  # type: ignore[assignment]

    # Rebuild so routes pick up the patched settings.
    app = create_app()

    yield TestClient(app)

    core.config.get_settings = original
    get_settings.cache_clear()


@pytest.fixture()
def auth_client():
    """TestClient with API_KEY=secret configured."""
    get_settings.cache_clear()

    # Monkeypatch the singleton
    import backend.core.config as cfg
    import backend.core.security as sec

    original_get = cfg.get_settings

    cfg.get_settings = lambda: Settings(api_key="secret")  # type: ignore[assignment]
    sec.get_settings = cfg.get_settings  # type: ignore[assignment]

    app = create_app()
    client = TestClient(app, raise_server_exceptions=True)
    yield client, "secret"

    cfg.get_settings = original_get
    sec.get_settings = original_get  # type: ignore[assignment]
    get_settings.cache_clear()


@pytest.fixture()
def open_client():
    """TestClient with no API_KEY (auth disabled)."""
    get_settings.cache_clear()

    import backend.core.config as cfg
    import backend.core.security as sec

    original_get = cfg.get_settings
    cfg.get_settings = lambda: Settings(api_key="")  # type: ignore[assignment]
    sec.get_settings = cfg.get_settings  # type: ignore[assignment]

    app = create_app()
    client = TestClient(app)
    yield client

    cfg.get_settings = original_get
    sec.get_settings = original_get  # type: ignore[assignment]
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# /health is always open (no API key dependency)
# ---------------------------------------------------------------------------

def test_health_always_open(open_client):
    resp = open_client.get("/health")
    assert resp.status_code == 200


def test_health_open_even_with_key_configured(auth_client):
    client, _ = auth_client
    resp = client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Data routes require API key when configured
# ---------------------------------------------------------------------------

def test_predictions_requires_key_when_configured(auth_client):
    client, _ = auth_client
    resp = client.get("/predictions")
    assert resp.status_code == 401


def test_predictions_accepts_correct_key(auth_client):
    client, key = auth_client
    resp = client.get("/predictions", headers={"X-API-Key": key})
    # 200 or 422/500 from missing DB — we just need it to NOT be 401.
    assert resp.status_code != 401


def test_predictions_rejects_wrong_key(auth_client):
    client, _ = auth_client
    resp = client.get("/predictions", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_data_routes_open_when_no_key_configured(open_client):
    """With API_KEY unset, routes are accessible without a header."""
    resp = open_client.get("/predictions")
    # Not 401 — may fail for DB reasons but auth is bypassed.
    assert resp.status_code != 401


# ---------------------------------------------------------------------------
# Production environment with no API_KEY set — fail closed
# ---------------------------------------------------------------------------

def test_production_without_api_key_fails_closed():
    """Empty API_KEY in production returns 500, not a silent bypass."""
    get_settings.cache_clear()

    import backend.core.config as cfg
    import backend.core.security as sec

    original_get = cfg.get_settings
    cfg.get_settings = lambda: Settings(api_key="", environment="production")  # type: ignore[assignment]
    sec.get_settings = cfg.get_settings  # type: ignore[assignment]

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/predictions")
    assert resp.status_code == 500

    cfg.get_settings = original_get
    sec.get_settings = original_get  # type: ignore[assignment]
    get_settings.cache_clear()
