"""Read-only Betway-first prices for ACCA research; never rewrites predictions."""
from collections import defaultdict
from datetime import timedelta
from math import isfinite
from statistics import median


def acca_prices(quotes, now):
    """Rank same-market books by median relative gap on >=3 shared fixtures.

    Only real, pre-kickoff quotes <=2h old qualify. Comparison pairs must
    be captured within five minutes; the target fixture is held out.
    """
    groups = defaultdict(list)
    for quote, kickoff in quotes:
        if (not isfinite(quote.decimal_odds) or quote.decimal_odds <= 1
                or quote.is_fallback or quote.source_type not in {"live", "api_football"}
                or not quote.fetched_at or not quote.bookmaker
                or not now - timedelta(hours=2) <= quote.fetched_at <= now
                or quote.fetched_at >= kickoff or kickoff <= now):
            continue
        groups[(quote.match_id, quote.market, quote.selection)].append(quote)
    comparisons = defaultdict(list)
    for (match_id, market, _), group in groups.items():
        betway = next((q for q in group if q.bookmaker.strip().casefold() == "betway"), None)
        if betway:
            for q in group:
                if q is not betway and abs((q.fetched_at - betway.fetched_at).total_seconds()) <= 300:
                    comparisons[(market, q.bookmaker)].append(
                        (match_id, abs(q.decimal_odds / betway.decimal_odds - 1)))
    output = []
    for (match_id, market, selection), group in groups.items():
        chosen = next((q for q in group if q.bookmaker.strip().casefold() == "betway"), None)
        count, gap = 0, None
        mode = "betway"
        if chosen is None:
            ranked = []
            for q in group:
                by_fixture = defaultdict(list)
                for fixture, difference in comparisons[(market, q.bookmaker)]:
                    if fixture != match_id:
                        by_fixture[fixture].append(difference)
                if len(by_fixture) >= 3:
                    distance = median(median(values) for values in by_fixture.values())
                    ranked.append((distance, -len(by_fixture), q.bookmaker, q))
            if ranked:
                gap, negative_count, _, chosen = min(ranked, key=lambda item: item[:3])
                count = -negative_count
                mode = "closest_observed"
            else:
                # No Betway comparison exists: use a real consensus-nearest
                # quote, explicitly WITHOUT claiming Betway similarity.
                midpoint = median(q.decimal_odds for q in group)
                chosen = min(group, key=lambda q: (abs(q.decimal_odds - midpoint), q.decimal_odds, q.bookmaker))
                mode = "market_reference"
        output.append(dict(match_id=match_id, market=market, selection=selection,
                           quote_id=chosen.id, bookmaker=chosen.bookmaker,
                           decimal_odds=chosen.decimal_odds,
                           fetched_at=chosen.fetched_at.isoformat(),
                           pricing_mode=mode,
                           comparison_fixtures=count, median_relative_gap=gap))
    return output
