"""API key authentication dependency.

All routes except /health are gated behind an ``X-API-Key`` header when
``API_KEY`` is configured in settings.  If ``API_KEY`` is empty (default in
development), authentication is bypassed so local iteration doesn't require
headers.

Usage in a router::

    from backend.core.security import ApiKeyDep

    @router.get("/some-endpoint")
    def handler(api_key: ApiKeyDep) -> ...:
        ...

The dependency resolves to the validated key string (or empty string when
auth is disabled).
"""

from __future__ import annotations

import re
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from backend.core.config import get_settings

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def _verify_api_key(key: str | None = Security(_header_scheme)) -> str:
    settings = get_settings()
    configured = settings.api_key.strip()
    if not configured:
        # Production with no API_KEY set is a misconfiguration — fail closed rather
        # than silently allowing all traffic through.
        if settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API_KEY is not configured on this server",
            )
        return ""
    if settings.environment == "production" and settings.secret_key.strip() in {
        "",
        "change-me",
    }:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SECRET_KEY is not configured on this server",
        )
    if not key or not secrets.compare_digest(key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return key


ApiKeyDep = Annotated[str, Depends(_verify_api_key)]

# Use this in APIRouter(dependencies=[...]) — can't use Annotated there.
RequireApiKey = Depends(_verify_api_key)


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def normalize_request_id(value: str | None) -> str:
    """Return a bounded, log-safe request ID or an empty value."""

    candidate = (value or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else ""
