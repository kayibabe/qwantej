"""Daily Picks: pure builder (qwantej.accumulator.daily) and the
backend.services.daily_tickets guarantee (SQLite, mirroring the other
accumulator persistence tests)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Prediction,
    Season,
    Team,
)
from backend.services.daily_tickets import ensure_daily_tickets, load_daily_candidates
from qwantej.accumulator.daily import (
    DAILY_LADDERS,
    DAILY_PRODUCTS,
    DailyCandidate,
    DailyProduct,
    build_daily_tickets,
)

NOW = datetime(2026, 9, 23, 9, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Pure builder
# ---------------------------------------------------------------------------


def _cand(
    i: int,
    odds: str,
    *,
    league: str | None = None,
    model_delta: float = 0.02,
    kickoff: datetime | None = None,
    captured: datetime | None = None,
) -> DailyCandidate:
    market_p = min(0.95, 0.95 / float(odds))
    return DailyCandidate(
        prediction_id=str(uuid.UUID(int=i + 1)),
        fixture_id=f"fx-{i:03d}",
        league_id=league or f"L{i % 6}",
        market="1X2",
        selection="home",
        kickoff_utc=kickoff or NOW + timedelta(hours=6),
        model_probability=max(0.01, min(0.99, market_p + model_delta)),
        market_probability=market_p,
        decimal_odds=Decimal(odds),
        captured_at=captured or NOW - timedelta(minutes=20),
        dqs=85.0,
    )


def _rich_pool() -> list[DailyCandidate]:
    prices = [
        "1.22", "1.30", "1.35", "1.40", "1.45", "1.50", "1.55", "1.62", "1.70", "1.80",
        "1.90", "2.00", "2.10", "2.25", "2.40", "2.60", "2.80", "3.00", "3.10", "1.28",
    ]
    return [_cand(i, p) for i, p in enumerate(prices)]


def _assert_ticket_invariants(result) -> None:
    fixtures = [leg.fixture_id for t in result.tickets for leg in t.legs]
    assert len(fixtures) == len(set(fixtures)), "a fixture appears on two tickets"
    for t in result.tickets:
        level = DAILY_LADDERS[t.product][t.rung]
        assert level.version == t.level_version
        assert level.min_legs <= len(t.legs) <= level.max_legs
        assert level.min_combined_odds <= t.combined_odds <= level.max_combined_odds
        leagues = [leg.league_id for leg in t.legs]
        assert max(leagues.count(x) for x in leagues) <= level.max_legs_per_league
        joint = 1.0
        odds = Decimal("1")
        for leg in t.legs:
            joint *= leg.estimated_probability
            odds *= leg.decimal_odds
        assert t.combined_odds == odds
        assert t.joint_probability == pytest.approx(joint)
        assert t.expected_return == pytest.approx(joint * float(odds))


def test_rich_slate_builds_all_three_products_at_preferred_rung() -> None:
    result = build_daily_tickets(_rich_pool(), as_of=NOW)

    assert [t.product for t in result.tickets] == list(DAILY_PRODUCTS)
    assert result.shortfall == ()
    assert all(t.rung == 0 for t in result.tickets)
    _assert_ticket_invariants(result)


def test_safe_ticket_maximises_joint_probability() -> None:
    result = build_daily_tickets(_rich_pool(), products=(DailyProduct.SAFE,), as_of=NOW)
    safe = result.tickets[0]
    # The heaviest favourites that clear the 1.80 minimum combined price.
    assert safe.joint_probability > 0.45
    assert all(leg.decimal_odds <= Decimal("1.80") for leg in safe.legs)


def test_builder_is_deterministic_regardless_of_input_order() -> None:
    pool = _rich_pool()
    baseline = build_daily_tickets(pool, as_of=NOW)
    shuffled = pool[:]
    random.Random(7).shuffle(shuffled)
    again = build_daily_tickets(shuffled, as_of=NOW)
    assert baseline == again


def test_stale_quotes_and_started_fixtures_are_never_used() -> None:
    pool = _rich_pool()
    stale = _cand(90, "1.20", captured=NOW - timedelta(hours=27))
    started = _cand(91, "1.21", kickoff=NOW - timedelta(minutes=1))
    future_quote = _cand(92, "1.19", captured=NOW + timedelta(minutes=1))
    result = build_daily_tickets([*pool, stale, started, future_quote], as_of=NOW)
    used = {leg.fixture_id for t in result.tickets for leg in t.legs}
    assert used.isdisjoint({"fx-090", "fx-091", "fx-092"})


def test_model_disagreement_filters_preferred_rung_only() -> None:
    # Every leg has the model 15pp below the market: rung 0 and 1 reject them
    # all, so the ticket must come from the last-resort rung — and say so.
    pool = [_cand(i, p, model_delta=-0.15) for i, p in enumerate(
        ["1.30", "1.40", "1.50", "1.60", "1.70", "1.80", "2.00", "2.20", "2.50", "3.00"]
    )]
    result = build_daily_tickets(pool, as_of=NOW)
    assert result.tickets, "last resort must still produce tickets"
    assert all(t.level_version == "daily-last-resort-v1" for t in result.tickets)
    _assert_ticket_invariants(result)


def test_thin_slate_falls_back_but_still_delivers_three_tickets() -> None:
    # Six fixtures, prices outside most preferred leg bands.
    pool = [_cand(i, p) for i, p in enumerate(["1.08", "1.09", "3.40", "3.60", "4.50", "5.50"])]
    result = build_daily_tickets(pool, as_of=NOW)
    assert len(result.tickets) == 3
    assert result.shortfall == ()
    assert any(t.rung > 0 for t in result.tickets)
    _assert_ticket_invariants(result)


def test_impossible_slate_reports_shortfall_instead_of_inventing_legs() -> None:
    pool = [_cand(i, p) for i, p in enumerate(["1.40", "1.50", "1.60"])]
    result = build_daily_tickets(pool, as_of=NOW)
    built = len(result.tickets)
    assert built >= 1
    assert built + len(result.shortfall) == 3
    assert len(result.shortfall) >= 1
    _assert_ticket_invariants(result)


def test_earlier_products_do_not_starve_later_ones() -> None:
    # Regression (review finding 1): greedy SAFE(2 legs) + BALANCED(3 legs)
    # consumed 5 of 6 legs and left BOLD short, although three disjoint
    # tickets were possible.
    pool = [
        _cand(i, p, league=f"L{i}")
        for i, p in enumerate(["1.40", "1.45", "1.50", "1.55", "1.60", "1.65"])
    ]
    result = build_daily_tickets(pool, as_of=NOW)
    assert len(result.tickets) == 3, result.shortfall
    assert result.shortfall == ()
    _assert_ticket_invariants(result)


def test_slate_of_only_heavy_favourites_still_yields_tickets() -> None:
    pool = [_cand(i, "1.05", league=f"L{i % 5}") for i in range(10)]
    result = build_daily_tickets(pool, as_of=NOW)
    assert len(result.tickets) >= 1
    _assert_ticket_invariants(result)


def test_quote_freshness_is_relaxed_rung_by_rung() -> None:
    five_hours = [_cand(i, p, captured=NOW - timedelta(hours=5))
                  for i, p in enumerate(_rich_pool_prices())]
    result = build_daily_tickets(five_hours, as_of=NOW)
    assert len(result.tickets) == 3
    assert all(t.rung >= 1 for t in result.tickets), "5h-old prices must not reach rung 0"
    day_old = [_cand(i, p, captured=NOW - timedelta(hours=20))
               for i, p in enumerate(_rich_pool_prices())]
    result = build_daily_tickets(day_old, as_of=NOW)
    assert len(result.tickets) == 3
    assert all(t.level_version == "daily-last-resort-v1" for t in result.tickets)


def _rich_pool_prices() -> list[str]:
    return [str(c.decimal_odds) for c in _rich_pool()]


def test_empty_pool_is_full_shortfall() -> None:
    result = build_daily_tickets([], as_of=NOW)
    assert result.tickets == ()
    assert result.shortfall == DAILY_PRODUCTS


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_probability": 1.0},
        {"market_probability": 0.0},
        {"decimal_odds": Decimal("1.00")},
        {"dqs": 101.0},
        {"kickoff_utc": datetime(2026, 9, 23, 12)},
        {"prediction_id": " "},
    ],
)
def test_candidate_validation_rejects_bad_inputs(overrides) -> None:
    base = dict(
        prediction_id="p", fixture_id="f", league_id="l", market="1X2", selection="home",
        kickoff_utc=NOW + timedelta(hours=3), model_probability=0.6,
        market_probability=0.58, decimal_odds=Decimal("1.60"),
        captured_at=NOW - timedelta(minutes=5), dqs=80.0,
    )
    base.update(overrides)
    with pytest.raises(ValueError):
        DailyCandidate(**base)


def test_naive_as_of_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_daily_tickets([], as_of=datetime(2026, 9, 23, 9))


# ---------------------------------------------------------------------------
# Service layer (SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


_HOME_PRICES = [
    "1.22", "1.30", "1.35", "1.40", "1.45", "1.50", "1.55", "1.62", "1.70", "1.80",
    "1.90", "2.00", "2.10", "2.25", "2.40", "2.60", "2.80", "3.00",
]


def _seed_slate(
    session: Session,
    *,
    prices: list[str] = _HOME_PRICES,
    kickoff: datetime = NOW + timedelta(hours=8),
    research_mode: bool = True,
    dqs: float = 82.0,
    quote_age: timedelta = timedelta(minutes=30),
    leagues: int = 6,
) -> list[tuple[Fixture, Prediction]]:
    comps = [Competition(name=f"League {n}") for n in range(leagues)]
    session.add_all(comps)
    session.flush()
    seasons = [Season(competition=c, label="2026") for c in comps]
    session.add_all(seasons)
    session.flush()
    out = []
    for i, price in enumerate(prices):
        home, away = Team(name=f"H{i}-{uuid.uuid4().hex[:6]}"), Team(name=f"A{i}")
        session.add_all([home, away])
        session.flush()
        fixture = Fixture(
            competition=comps[i % leagues], season=seasons[i % leagues],
            home_team=home, away_team=away, kickoff_utc=kickoff,
            status=FixtureStatus.SCHEDULED,
        )
        session.add(fixture)
        session.flush()
        home_odds = Decimal(price)
        prediction = _add_prediction(session, fixture, home_odds, research_mode, dqs)
        _add_market(session, fixture, home_odds, captured=NOW - quote_age)
        out.append((fixture, prediction))
    session.flush()
    return out


def _add_prediction(session, fixture, home_odds, research_mode, dqs, *,
                    market="1X2", selection="home") -> Prediction:
    p = min(0.93, 0.93 / float(home_odds))
    prediction = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=NOW - timedelta(hours=20),
        decision_as_of=NOW - timedelta(hours=20),
        market=market,
        selection=selection,
        ensemble_probability=p,
        calibrated_probability=p,
        conservative_probability=max(0.001, p - 0.05),
        dqs=dqs,
        qss=dqs,
        research_mode=research_mode,
        gate_passed=False,
    )
    session.add(prediction)
    session.flush()
    return prediction


def _add_market(session, fixture, home_odds: Decimal, *, captured: datetime,
                bookmaker: str = "Book", selections=("home", "draw", "away")) -> None:
    implied_home = 1 / float(home_odds)
    rest = max(0.05, 1.05 - implied_home)
    prices = {
        "home": home_odds,
        "draw": Decimal(str(round(1 / (rest * 0.45), 2))),
        "away": Decimal(str(round(1 / (rest * 0.55), 2))),
    }
    for sel in selections:
        session.add(OddsQuote(
            fixture_id=fixture.id, bookmaker=bookmaker, market="1X2", selection=sel,
            decimal_odds=prices[sel], captured_at=captured, source="test",
        ))


def test_ensure_creates_three_paper_unstaked_tickets_with_lineage(session) -> None:
    _seed_slate(session)

    run = ensure_daily_tickets(session, now=NOW)
    session.flush()

    assert run.shortfall == []
    assert len(run.created) == 3 and run.total_today == 3
    accs = session.scalars(select(Accumulator)).all()
    assert sorted(a.product for a in accs) == sorted(p.value for p in DAILY_PRODUCTS)
    for acc in accs:
        assert acc.paper_only is True
        assert acc.stake is None
        assert acc.optimiser_version == "daily-ticket-v1"
        assert acc.input_manifest_hash
    legs = session.scalars(select(AccumulatorLeg)).all()
    assert len({leg.fixture_id for leg in legs}) == len(legs)
    for leg in legs:
        prediction = session.get(Prediction, leg.prediction_id)
        assert prediction.accumulator_id == leg.accumulator_id
        assert leg.bookmaker == "Book" and leg.quote_captured_at is not None


def test_ensure_is_idempotent_within_a_utc_day(session) -> None:
    _seed_slate(session)
    first = ensure_daily_tickets(session, now=NOW)
    session.flush()
    second = ensure_daily_tickets(session, now=NOW + timedelta(hours=5))
    assert len(first.created) == 3
    assert second.created == [] and second.existing_today == 3
    assert len(session.scalars(select(Accumulator)).all()) == 3


def test_ensure_builds_only_missing_products(session) -> None:
    _seed_slate(session)
    ensure_daily_tickets(session, now=NOW, target=1)
    session.flush()
    run = ensure_daily_tickets(session, now=NOW + timedelta(minutes=5), target=3)
    assert run.existing_today == 1
    assert sorted(t.product for t in run.tickets) == [DailyProduct.BALANCED, DailyProduct.BOLD]
    products = [a.product for a in session.scalars(select(Accumulator))]
    assert sorted(products) == sorted(p.value for p in DAILY_PRODUCTS)


def test_next_day_gets_a_fresh_set(session) -> None:
    _seed_slate(session)
    ensure_daily_tickets(session, now=NOW)
    session.flush()
    tomorrow = NOW + timedelta(days=1)
    # Tomorrow's slate, priced 30 minutes before tomorrow's run.
    _seed_slate(
        session, kickoff=tomorrow + timedelta(hours=8),
        quote_age=timedelta(minutes=30) - timedelta(days=1),
    )
    run = ensure_daily_tickets(session, now=tomorrow)
    assert run.existing_today == 0
    assert len(run.created) == 3


def test_target_zero_is_a_no_op(session) -> None:
    _seed_slate(session)
    run = ensure_daily_tickets(session, now=NOW, target=0)
    assert run.created == [] and run.shortfall == []
    assert session.scalars(select(Accumulator)).all() == []


def test_low_dqs_stale_or_incoherent_markets_are_excluded(session) -> None:
    good = _seed_slate(session, prices=["1.40", "1.50"], leagues=2)
    low_dqs = _seed_slate(session, prices=["1.30"], dqs=55.0, leagues=1)
    stale = _seed_slate(session, prices=["1.35"], quote_age=timedelta(hours=30), leagues=1)
    # Incoherent: the bookmaker never quoted the draw.
    comp = Competition(name="Incoherent")
    season = Season(competition=comp, label="2026")
    h, a = Team(name="IH"), Team(name="IA")
    session.add_all([comp, season, h, a])
    session.flush()
    fx = Fixture(competition=comp, season=season, home_team=h, away_team=a,
                 kickoff_utc=NOW + timedelta(hours=8), status=FixtureStatus.SCHEDULED)
    session.add(fx)
    session.flush()
    _add_prediction(session, fx, Decimal("1.45"), True, 80.0)
    _add_market(session, fx, Decimal("1.45"), captured=NOW - timedelta(minutes=10),
                selections=("home", "away"))
    session.flush()

    ids = {c.fixture_id for c in load_daily_candidates(
        session, now=NOW, lookahead=timedelta(hours=30))}
    assert ids == {str(f.id) for f, _ in good}
    assert str(low_dqs[0][0].id) not in ids and str(stale[0][0].id) not in ids
    assert str(fx.id) not in ids


def test_production_forecast_preferred_over_research_for_same_fixture(session) -> None:
    [(fixture, research_pred)] = _seed_slate(session, prices=["1.50"], leagues=1)
    production_pred = _add_prediction(session, fixture, Decimal("1.50"), False, 80.0)
    session.flush()
    [cand] = load_daily_candidates(session, now=NOW, lookahead=timedelta(hours=30))
    assert cand.prediction_id == str(production_pred.id)
    assert cand.prediction_id != str(research_pred.id)


def test_archived_draw_away_and_btts_are_repriced_from_complete_markets(session) -> None:
    pairs = _seed_slate(session, prices=["1.50", "1.60", "1.70"], leagues=3)
    draw_fixture, away_fixture, btts_fixture = (pair[0] for pair in pairs)
    draw = _add_prediction(session, draw_fixture, Decimal("3.50"), False, 80.0,
                           selection="draw")
    away = _add_prediction(session, away_fixture, Decimal("2.80"), False, 80.0,
                           selection="away")
    btts = _add_prediction(session, btts_fixture, Decimal("1.80"), False, 80.0,
                           market="BTTS", selection="yes")
    for selection, odds in (("yes", "1.80"), ("no", "2.05")):
        session.add(OddsQuote(
            fixture_id=btts_fixture.id, bookmaker="Book", market="BTTS",
            selection=selection, decimal_odds=Decimal(odds),
            captured_at=NOW - timedelta(minutes=15), source="test",
        ))
    session.flush()

    candidates = load_daily_candidates(session, now=NOW, lookahead=timedelta(hours=30))
    by_prediction = {c.prediction_id: c for c in candidates}
    assert by_prediction[str(draw.id)].market == "1X2"
    assert by_prediction[str(draw.id)].selection == "draw"
    assert by_prediction[str(away.id)].selection == "away"
    assert by_prediction[str(btts.id)].market == "BTTS"
    assert by_prediction[str(btts.id)].selection == "yes"
    assert by_prediction[str(btts.id)].decimal_odds == Decimal("1.80")


def test_incomplete_or_mixed_bookmaker_btts_is_excluded(session) -> None:
    [(fixture, _)] = _seed_slate(session, prices=["1.50"], leagues=1)
    prediction = _add_prediction(session, fixture, Decimal("1.80"), False, 80.0,
                                 market="BTTS", selection="yes")
    for bookmaker, selection in (("Book A", "yes"), ("Book B", "no")):
        session.add(OddsQuote(
            fixture_id=fixture.id, bookmaker=bookmaker, market="BTTS",
            selection=selection, decimal_odds=Decimal("1.90"),
            captured_at=NOW - timedelta(minutes=15), source="test",
        ))
    session.flush()
    candidates = load_daily_candidates(session, now=NOW, lookahead=timedelta(hours=30))
    assert str(prediction.id) not in {c.prediction_id for c in candidates}


def test_daily_ticket_persists_archived_btts_market(session) -> None:
    pairs = _seed_slate(session, prices=["1.50", "1.60"], leagues=2)
    fixture, home_prediction = pairs[0]
    # Keep the second fixture's home forecast, but leave this fixture with BTTS only.
    session.delete(home_prediction)
    btts = _add_prediction(session, fixture, Decimal("1.80"), False, 80.0,
                           market="BTTS", selection="yes")
    for selection, odds in (("yes", "1.80"), ("no", "2.05")):
        session.add(OddsQuote(
            fixture_id=fixture.id, bookmaker="Book", market="BTTS",
            selection=selection, decimal_odds=Decimal(odds),
            captured_at=NOW - timedelta(minutes=15), source="test",
        ))
    session.flush()

    run = ensure_daily_tickets(session, now=NOW, target=1)
    assert len(run.created) == 1
    assert run.created[0].paper_only is True
    leg = session.scalars(select(AccumulatorLeg).where(
        AccumulatorLeg.prediction_id == btts.id
    )).one()
    assert (leg.market_family, leg.selection) == ("BTTS", "yes")


def test_fixture_already_on_a_ticket_is_not_reused(session) -> None:
    pairs = _seed_slate(session, prices=["1.40", "1.50", "1.60"], leagues=3)
    fixture, _ = pairs[0]
    # Another forecast for the same fixture already backs a ticket.
    other = _add_prediction(session, fixture, Decimal("1.40"), False, 80.0)
    other.accumulator_id = uuid.uuid4()
    session.flush()
    ids = {c.fixture_id for c in load_daily_candidates(
        session, now=NOW, lookahead=timedelta(hours=30))}
    assert str(fixture.id) not in ids


def test_fallback_lookahead_used_when_today_is_thin(session) -> None:
    # Only 2 fixtures today; the rest kick off in ~2 days (inside 72h).
    _seed_slate(session, prices=["1.40", "1.55"], leagues=2)
    _seed_slate(session, prices=_HOME_PRICES[:12], kickoff=NOW + timedelta(hours=50))
    run = ensure_daily_tickets(session, now=NOW)
    assert run.shortfall == []
    assert len(run.created) == 3


def test_shortfall_is_reported_when_nothing_is_priced(session) -> None:
    _seed_slate(session, prices=["1.40"], quote_age=timedelta(hours=30), leagues=1)
    run = ensure_daily_tickets(session, now=NOW)
    assert run.created == []
    assert run.shortfall == list(DAILY_PRODUCTS)


def test_nothing_is_built_before_the_build_hour(session) -> None:
    _seed_slate(session)
    early = NOW.replace(hour=4)
    run = ensure_daily_tickets(session, now=early, build_hour_utc=6)
    assert run.created == [] and run.shortfall == []
    later = ensure_daily_tickets(session, now=NOW, build_hour_utc=6)  # 09:30 UTC
    assert len(later.created) == 3


def test_forecasts_made_after_the_cutoff_are_not_used(session) -> None:
    [(fixture, prediction)] = _seed_slate(session, prices=["1.50"], leagues=1)
    prediction.prediction_timestamp = NOW + timedelta(seconds=1)
    prediction.decision_as_of = NOW + timedelta(seconds=1)
    session.flush()
    assert load_daily_candidates(session, now=NOW, lookahead=timedelta(hours=30)) == []


def test_naive_now_rejected(session) -> None:
    with pytest.raises(ValueError):
        ensure_daily_tickets(session, now=datetime(2026, 9, 23, 9))
