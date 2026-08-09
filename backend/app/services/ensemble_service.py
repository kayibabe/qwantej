"""
ensemble_service.py — Orchestrate the Phase 1B ensemble pipeline.

For a given fixture date and horizon:
  1. Load HistoricalFixtures (same league/teams, last N seasons) → fit ZINB + Elo
  2. Load live Fixture rows for the date → for each fixture:
     a. Run ZINBMarketsModel → market probs
     b. Run EloSystem → 1X2 probs
     c. Pull Bayesian probs from existing Signal rows (already computed by
        signal_engine.py) or directly from market_snapshots
     d. Run EnsembleEngine → EnsembleResult per market
     e. Archive ForecastSnapshot rows (one per fixture × market)
  3. Return summary counts

This replaces the old signal_engine.py compute path for Phase 1B onward.
The old Signal table is still written by the legacy pipeline during the
transition; ForecastSnapshot is the new canonical archive.

Usage (from scheduler or CLI):
    asyncio.run(compute_snapshots_for_date(db, date.today(), horizon="D-1"))
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ensemble import EnsembleEngine
from app.engines.zinb_markets import ZINBMarketsModel
from app.engines.elo import EloSystem
from app.models.elo_rating import EloRating
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.historical_fixture import HistoricalFixture
from app.models.fixture import Fixture
from app.models.signal import Signal

logger = logging.getLogger(__name__)

_HISTORY_SEASONS = 3   # seasons of historical data to fit ZINB + Elo
_MIN_HISTORY = 10      # minimum matches needed before ZINB is trusted


async def compute_snapshots_for_date(
    db: AsyncSession,
    fixture_date: date,
    horizon: str = "D-1",
) -> dict[str, int]:
    """
    Run the ensemble for all fixtures on fixture_date and archive ForecastSnapshots.

    Returns a summary dict: {total, signals, no_signals, fixtures_processed}
    """
    snapshot_at = datetime.now(tz=timezone.utc)
    summary = {"total": 0, "signals": 0, "no_signals": 0, "fixtures_processed": 0}

    # --- Load live fixtures for the target date ---
    result = await db.execute(
        select(Fixture).where(Fixture.event_date == fixture_date)
    )
    fixtures = result.scalars().all()
    if not fixtures:
        logger.info("ensemble_service: no fixtures for %s", fixture_date)
        return summary

    logger.info("ensemble_service: processing %d fixtures for %s (horizon=%s)",
                len(fixtures), fixture_date, horizon)

    for fixture in fixtures:
        n = await _process_fixture(db, fixture, snapshot_at, horizon)
        summary["total"] += n["total"]
        summary["signals"] += n["signals"]
        summary["no_signals"] += n["no_signals"]
        summary["fixtures_processed"] += 1

    logger.info("ensemble_service: done — %s", summary)
    return summary


async def _process_fixture(
    db: AsyncSession,
    fixture: Fixture,
    snapshot_at: datetime,
    horizon: str,
) -> dict[str, int]:
    home = fixture.home_team
    away = fixture.away_team
    league = fixture.league or ""
    country = fixture.country or ""

    # 1. Load historical matches for ZINB + Elo fitting
    hist_matches = await _load_history(db, league, country)

    # 2. Fit ZINB
    zinb_model = ZINBMarketsModel()
    if len(hist_matches) >= _MIN_HISTORY:
        zinb_model.fit(hist_matches)
    zinb_probs = zinb_model.predict_market_probs(home, away)
    lambda_home, lambda_away = (
        zinb_model.predict_lambdas(home, away)
        if zinb_model._model.fitted else (None, None)
    )

    # 3. Load or fit Elo
    elo_home_rating, elo_away_rating, elo_1x2 = await _elo_predict(
        db, home, away, league, country, hist_matches
    )

    # 4. Pull Bayesian probs from existing Signal rows for this fixture
    bayesian_probs = await _load_bayesian_probs(db, fixture.id)

    # 5. Pull market odds from Signal rows (best available per market)
    market_odds = await _load_market_odds(db, fixture.id)

    # 6. Run ensemble
    engine = EnsembleEngine()
    results = engine.compute(
        zinb_probs=zinb_probs,
        bayesian_probs=bayesian_probs,
        elo_1x2=elo_1x2,
        market_odds=market_odds,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        elo_home=elo_home_rating,
        elo_away=elo_away_rating,
    )

    # 7. Archive ForecastSnapshot rows
    counts = {"total": 0, "signals": 0, "no_signals": 0}
    for r in results:
        snap = ForecastSnapshot(
            fixture_id=fixture.id,
            historical_fixture_id=None,
            snapshot_at=snapshot_at,
            horizon=horizon,
            market=r.market,
            zinb_prob=r.zinb_prob,
            bayesian_prob=r.bayesian_prob,
            elo_prob=r.elo_prob,
            ensemble_prob=r.ensemble_prob,
            calibrated_prob=None,
            signal_type=r.signal_type,
            confidence=r.confidence,
            data_quality_score=r.data_quality_score,
            fair_odds=r.fair_odds,
            market_odds=r.market_odds,
            value_edge=r.value_edge,
            is_value_bet=r.is_value_bet,
            lambda_home=r.lambda_home,
            lambda_away=r.lambda_away,
            elo_home=r.elo_home,
            elo_away=r.elo_away,
            model_version=r.model_version,
        )
        db.add(snap)
        counts["total"] += 1
        if r.signal_type == "SIGNAL":
            counts["signals"] += 1
        else:
            counts["no_signals"] += 1

    await db.commit()
    return counts


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _load_history(
    db: AsyncSession,
    league: str,
    country: str,
) -> list[dict]:
    """Load recent historical matches for the league to fit ZINB + Elo."""
    from sqlalchemy import and_
    result = await db.execute(
        select(
            HistoricalFixture.home_team,
            HistoricalFixture.away_team,
            HistoricalFixture.home_goals,
            HistoricalFixture.away_goals,
            HistoricalFixture.match_date,
        ).where(
            and_(
                HistoricalFixture.league == league,
                HistoricalFixture.home_goals.is_not(None),
                HistoricalFixture.away_goals.is_not(None),
            )
        ).order_by(HistoricalFixture.match_date.asc())
    )
    rows = result.all()
    return [
        {
            "home_team": r.home_team,
            "away_team": r.away_team,
            "home_goals": r.home_goals,
            "away_goals": r.away_goals,
            "match_date": r.match_date.isoformat() if r.match_date else "",
        }
        for r in rows
    ]


async def _elo_predict(
    db: AsyncSession,
    home: str,
    away: str,
    league: str,
    country: str,
    hist_matches: list[dict],
) -> tuple[Optional[float], Optional[float], Optional[tuple[float, float, float]]]:
    """
    Load persisted Elo ratings from DB, or fit from historical matches if not present.
    Returns (elo_home_rating, elo_away_rating, (p_home, p_draw, p_away)).
    """
    # Try to load from elo_ratings table
    result = await db.execute(
        select(EloRating).where(
            EloRating.league == league,
            EloRating.team_name.in_([home, away]),
        ).order_by(EloRating.season.desc())
    )
    stored = {r.team_name: r for r in result.scalars().all()}

    elo = EloSystem()

    if home in stored and away in stored:
        elo.load_records([
            {"team_name": r.team_name, "rating": r.rating, "n_matches": r.n_matches,
             "last_match_date": r.last_match_date}
            for r in stored.values()
        ])
    elif hist_matches:
        # Fit from warehouse data and persist
        elo.fit(hist_matches)
        await _persist_elo(db, elo, league, country)
    else:
        return None, None, None

    elo_home = elo.get_rating(home)
    elo_away = elo.get_rating(away)
    p1x2 = elo.predict_1x2(home, away)
    return elo_home, elo_away, p1x2


async def _persist_elo(
    db: AsyncSession,
    elo: EloSystem,
    league: str,
    country: str,
) -> None:
    """Upsert Elo ratings into the elo_ratings table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import date as _date

    current_season = _date.today().year if _date.today().month >= 7 else _date.today().year - 1
    records = elo.to_records(league, country, current_season)

    for rec in records:
        stmt = (
            pg_insert(EloRating)
            .values(**rec)
            .on_conflict_do_update(
                constraint="uq_elo_ratings_team_league_season",
                set_={
                    "rating": rec["rating"],
                    "n_matches": rec["n_matches"],
                    "last_match_date": rec["last_match_date"],
                },
            )
        )
        await db.execute(stmt)
    await db.commit()


async def _load_bayesian_probs(
    db: AsyncSession,
    fixture_id: int,
) -> dict[str, float]:
    """Pull derived_prob from existing Signal rows for the fixture (Bayesian engine output)."""
    from app.engines.zinb_markets import PHASE1A_MARKETS
    result = await db.execute(
        select(Signal.market, Signal.bayesian_prob).where(
            Signal.fixture_id == fixture_id,
            Signal.market.in_(PHASE1A_MARKETS),
        )
    )
    probs: dict[str, float] = {}
    for market, prob in result.all():
        if prob is not None and 0 < prob < 1:
            probs[market] = float(prob)
    return probs


async def _load_market_odds(
    db: AsyncSession,
    fixture_id: int,
) -> dict[str, float]:
    """Pull best bookmaker odds from Signal rows for the fixture."""
    from app.engines.zinb_markets import PHASE1A_MARKETS
    result = await db.execute(
        select(Signal.market, Signal.bayesian_best_odd).where(
            Signal.fixture_id == fixture_id,
            Signal.market.in_(PHASE1A_MARKETS),
        )
    )
    odds: dict[str, float] = {}
    for market, best_odd in result.all():
        if best_odd is not None and best_odd > 1.0:
            odds[market] = float(best_odd)
    return odds
