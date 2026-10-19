from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.acca_pricing import acca_prices

NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)


def quote(match, book, price, **kwargs):
    values = dict(id=match * 10, match_id=match, market="home_win", selection="Home",
                  bookmaker=book, decimal_odds=price, fetched_at=NOW,
                  source_type="live", is_fallback=False)
    values.update(kwargs)
    return SimpleNamespace(**values), NOW + timedelta(hours=1)


def comparisons():
    return [q for match in range(1, 4) for q in (
        quote(match, "Betway", 2), quote(match, "Close", 2.02), quote(match, "Highest", 2.5))]


def test_betway_first_then_closest_not_highest():
    rows = acca_prices(comparisons() + [quote(4, "Close", 1.8), quote(4, "Highest", 2.6)], NOW)
    assert rows[0]["bookmaker"] == "Betway"
    fallback = next(row for row in rows if row["match_id"] == 4)
    assert fallback["bookmaker"] == "Close"
    assert fallback["decimal_odds"] == 1.8
    assert fallback["comparison_fixtures"] == 3


def test_insufficient_comparisons_do_not_claim_similarity():
    rows = acca_prices([quote(4, "Close", 1.8), quote(4, "Middle", 2), quote(4, "High", 3)], NOW)
    assert rows[0]["pricing_mode"] == "market_reference"
    assert rows[0]["bookmaker"] == "Middle"
    assert rows[0]["median_relative_gap"] is None


def test_provider_quotes_and_case_insensitive_betway():
    rows = acca_prices([quote(4, "BETWAY", 1.8, source_type="api_football")], NOW)
    assert rows[0]["pricing_mode"] == "betway"


def test_stale_synthetic_future_and_in_play_prices_rejected():
    for overrides in [dict(fetched_at=NOW - timedelta(hours=3)), dict(is_fallback=True),
                      dict(source_type="synthetic"), dict(decimal_odds=float("nan")),
                      dict(fetched_at=NOW + timedelta(seconds=1))]:
        assert acca_prices([quote(4, "Betway", 2, **overrides)], NOW) == []
    row, _ = quote(4, "Betway", 2)
    assert acca_prices([(row, NOW)], NOW) == []


def test_stale_betway_uses_comparable_live_alternative():
    rows = acca_prices(comparisons() + [quote(4, "Betway", 2, fetched_at=NOW - timedelta(hours=3)),
                                       quote(4, "Close", 1.8)], NOW)
    assert next(row for row in rows if row["match_id"] == 4)["bookmaker"] == "Close"


def test_other_markets_and_unsynchronised_pairs_do_not_qualify():
    for overrides in [dict(market="away_win"), dict(fetched_at=NOW - timedelta(minutes=6))]:
        pairs = [q for match in range(1, 4) for q in (
            quote(match, "Betway", 2), quote(match, "Close", 2.02, **overrides))]
        rows = acca_prices(pairs + [quote(4, "Close", 2)], NOW)
        assert next(row for row in rows if row["match_id"] == 4)["pricing_mode"] == "market_reference"
