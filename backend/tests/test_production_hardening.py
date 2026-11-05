"""Production exposure and response-hardening checks."""

from app.main import _api_docs_config


def test_production_disables_interactive_and_schema_docs():
    assert _api_docs_config("production") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_non_production_keeps_interactive_docs():
    assert _api_docs_config("development") == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
