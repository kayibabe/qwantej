"""Small authenticated API-Football v3 client with injectable HTTP transport."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

from backend.core.config import Settings


class ApiFootballError(RuntimeError):
    """Provider or transport failure that never includes the API credential."""


class JsonTransport(Protocol):
    def get_json(
        self, url: str, *, headers: Mapping[str, str], timeout_seconds: float
    ) -> tuple[int, Mapping[str, str], Mapping[str, Any]]: ...


class UrllibJsonTransport:
    """Standard-library transport; tests inject an in-memory replacement."""

    def get_json(
        self, url: str, *, headers: Mapping[str, str], timeout_seconds: float
    ) -> tuple[int, Mapping[str, str], Mapping[str, Any]]:
        request = Request(url, headers=dict(headers), method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ApiFootballError("API-Football returned a non-object response")
            return response.status, dict(response.headers.items()), payload


@dataclass(frozen=True)
class ApiPage:
    response: tuple[dict[str, Any], ...]
    current_page: int
    total_pages: int
    requests_remaining: int | None


class ApiFootballClient:
    """GET-only client for fixtures, pre-match odds, and fixture statistics."""

    QUOTA_WARNING_THRESHOLD = 200

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://v3.football.api-sports.io",
        timeout_seconds: float = 30.0,
        quota_warning_threshold: int = QUOTA_WARNING_THRESHOLD,
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("API_FOOTBALL_KEY is required")
        if not base_url.startswith("https://"):
            raise ValueError("API-Football base_url must use HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._quota_warning_threshold = quota_warning_threshold
        self._transport = transport or UrllibJsonTransport()

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: JsonTransport | None = None
    ) -> ApiFootballClient:
        return cls(
            api_key=settings.api_football_key,
            base_url=settings.api_football_base_url,
            timeout_seconds=settings.api_football_timeout_seconds,
            transport=transport,
        )

    def fixtures(self, **parameters: str | int) -> tuple[dict[str, Any], ...]:
        return self._all_pages("fixtures", parameters)

    def odds(self, **parameters: str | int) -> tuple[dict[str, Any], ...]:
        return self._all_pages("odds", parameters)

    def fixture_statistics(self, fixture_id: int) -> tuple[dict[str, Any], ...]:
        return self._all_pages("fixtures/statistics", {"fixture": fixture_id})

    def _all_pages(
        self, endpoint: str, parameters: Mapping[str, str | int]
    ) -> tuple[dict[str, Any], ...]:
        page = self._get_page(endpoint, parameters)
        self._check_quota(page)
        collected = list(page.response)
        while page.current_page < page.total_pages:
            page = self._get_page(
                endpoint, {**parameters, "page": page.current_page + 1}
            )
            self._check_quota(page)
            collected.extend(page.response)
        return tuple(collected)

    def _check_quota(self, page: ApiPage) -> None:
        remaining = page.requests_remaining
        if remaining is not None and remaining <= self._quota_warning_threshold:
            log.warning(
                "API-Football quota low: %d request(s) remaining", remaining
            )

    def _get_page(
        self, endpoint: str, parameters: Mapping[str, str | int]
    ) -> ApiPage:
        query = urlencode(sorted((key, str(value)) for key, value in parameters.items()))
        url = f"{self._base_url}/{endpoint.lstrip('/')}?{query}"
        try:
            status, response_headers, payload = self._transport.get_json(
                url,
                headers={"Accept": "application/json", "x-apisports-key": self._api_key},
                timeout_seconds=self._timeout_seconds,
            )
        except OSError as exc:
            raise ApiFootballError("API-Football transport failed") from exc
        if status < 200 or status >= 300:
            raise ApiFootballError(f"API-Football request failed with HTTP {status}")
        errors = payload.get("errors")
        if errors not in (None, [], {}):
            raise ApiFootballError(f"API-Football rejected the request: {_safe_errors(errors)}")
        raw_response = payload.get("response")
        if not isinstance(raw_response, list) or not all(
            isinstance(item, dict) for item in raw_response
        ):
            raise ApiFootballError("API-Football response field must be a list of objects")
        paging = payload.get("paging") or {"current": 1, "total": 1}
        if not isinstance(paging, dict):
            raise ApiFootballError("API-Football paging field must be an object")
        current = _positive_int(paging.get("current", 1), "paging.current")
        total = _positive_int(paging.get("total", 1), "paging.total")
        if current > total:
            raise ApiFootballError("API-Football paging.current exceeds paging.total")
        remaining = _optional_int(response_headers.get("x-ratelimit-requests-remaining"))
        return ApiPage(tuple(raw_response), current, total, remaining)


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiFootballError(f"API-Football {field} must be an integer") from exc
    if parsed < 1:
        raise ApiFootballError(f"API-Football {field} must be positive")
    return parsed


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_errors(value: Any) -> str:
    """Keep provider diagnostics useful without echoing arbitrary payloads."""

    if isinstance(value, dict):
        return ", ".join(str(key) for key in sorted(value)) or "unknown error"
    if isinstance(value, list):
        return f"{len(value)} error(s)"
    return "provider error"
