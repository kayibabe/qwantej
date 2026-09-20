"""Tests for API key authentication (backend.core.security) and the
environment fail-closed policy (backend.main._validate_environment_config)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings, get_settings
from backend.main import _validate_environment_config, create_app


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
# Environment fail-closed policy: only "development" may run unconfigured.
# Everything else — "production", "staging", CI, or an unset/typo'd value —
# must have API_KEY, SECRET_KEY and CORS_ORIGINS all set, or refuse to boot.
# ---------------------------------------------------------------------------

_FULLY_CONFIGURED = {
    "api_key": "secret",
    "secret_key": "a-real-secret",
    "cors_origins": "https://app.example.com",
}


@pytest.mark.parametrize("environment", ["production", "staging", "ci", "prod", "", "Production"])
def test_non_development_environment_unconfigured_fails_validation(environment):
    """Any non-'development' value with missing config must fail closed."""
    settings = Settings(environment=environment)
    with pytest.raises(RuntimeError):
        _validate_environment_config(settings)


@pytest.mark.parametrize("environment", ["production", "staging", "ci"])
def test_non_development_environment_fully_configured_passes_validation(environment):
    """The same environments boot fine once real config is supplied."""
    settings = Settings(environment=environment, **_FULLY_CONFIGURED)
    _validate_environment_config(settings)  # must not raise


def test_development_environment_passes_validation_even_when_unconfigured():
    """Only the explicit 'development' value gets the relaxed default."""
    settings = Settings(environment="development")
    _validate_environment_config(settings)  # must not raise


def test_secret_key_default_change_me_fails_validation_outside_development():
    settings = Settings(environment="production", api_key="secret", cors_origins="https://x")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _validate_environment_config(settings)


def test_missing_cors_origins_fails_validation_outside_development():
    settings = Settings(
        environment="staging", api_key="secret", secret_key="a-real-secret", cors_origins=""
    )
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        _validate_environment_config(settings)


# NOTE: backend.main and backend.core.security each do ``from
# backend.core.config import get_settings`` — that binds the name in their
# own module namespace at import time. Patching backend.core.config's
# attribute alone does not affect create_app()'s already-bound name, so
# these tests patch ``backend.main.get_settings`` (and, for auth-dependent
# assertions, ``backend.core.security.get_settings``) directly.

def test_create_app_refuses_to_boot_for_misconfigured_production(monkeypatch):
    """create_app() itself must fail — not just return an app that 500s per request."""
    import backend.core.security as sec
    import backend.main as main

    bad_settings = Settings(api_key="", environment="production")
    monkeypatch.setattr(main, "get_settings", lambda: bad_settings)
    monkeypatch.setattr(sec, "get_settings", lambda: bad_settings)

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_boots_for_fully_configured_staging(monkeypatch):
    """A staging environment with real config boots and enforces auth normally."""
    import backend.core.security as sec
    import backend.main as main

    staging_settings = Settings(environment="staging", **_FULLY_CONFIGURED)
    monkeypatch.setattr(main, "get_settings", lambda: staging_settings)
    monkeypatch.setattr(sec, "get_settings", lambda: staging_settings)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/predictions").status_code == 401
    # 200 or 500 depending on DB availability — we only need it to NOT be 401.
    assert client.get("/predictions", headers={"X-API-Key": "secret"}).status_code != 401
    assert client.get("/docs").status_code == 404, "docs must stay closed outside development"


def test_docs_enabled_in_development_only(monkeypatch):
    import backend.main as main

    monkeypatch.setattr(main, "get_settings", lambda: Settings(environment="development"))

    app = create_app()
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
