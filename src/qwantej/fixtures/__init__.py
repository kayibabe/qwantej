"""Fixture ingestion and normalization into canonical entities."""

from qwantej.fixtures.api_football import (
    ApiFootballFixture,
    ApiFootballOddsQuote,
    ApiFootballPayloadError,
    normalize_fixture_status,
    normalize_selection,
    parse_fixture,
    parse_odds,
)

__all__ = [
    "ApiFootballFixture",
    "ApiFootballOddsQuote",
    "ApiFootballPayloadError",
    "normalize_fixture_status",
    "normalize_selection",
    "parse_fixture",
    "parse_odds",
]
