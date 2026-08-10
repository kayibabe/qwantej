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

from app.engines.ensemble import EnsembleEngine, MODEL_VERSION
from app.engines.zinb_markets import ZINBMarketsModel
from app.engines.elo import EloSystem
from app.models.calibration_record import CalibrationRecord
from app.models.elo_rating import EloRating
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.historical_fixture import HistoricalFixture
from app.models.fixture import Fixture
from app.models.odds import MarketSnapshot
from app.services.calibration_service import apply_calibration_knots
from app.services.market_preprocessing import (
    latest_snapshots, build_cs_by_bookie, build_goals_ou, build_match_winner,
    build_double_chance, build_home_totals, build_away_totals,
    build_win_to_nil_home, build_win_to_nil_away, build_exact_goals,
    build_goals_first_half, build_goals_second_half,
)

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
    from collections import defaultdict

    snapshot_at = datetime.now(tz=timezone.utc)
    summary = {"total": 0, "signals": 0, "no_signals": 0, "fixtures_processed": 0}

    # --- Load active calibration knots (one per market, cache for this run) ---
    cal_result = await db.execute(
        select(CalibrationRecord.market, CalibrationRecord.calibration_knots_json).where(
            CalibrationRecord.is_active.is_(True),
            CalibrationRecord.model_version == MODEL_VERSION,
        )
    )
    calibrators: dict[str, str] = {market: knots for market, knots in cal_result.all()}
    if calibrators:
        logger.info("ensemble_service: loaded calibrators for %d markets", len(calibrators))

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

    # --- Group fixtures by league so models are fitted once per league, not per fixture ---
    by_league: dict[tuple[str, str], list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        by_league[(fixture.league or "", fixture.country or "")].append(fixture)

    logger.info("ensemble_service: %d distinct leagues", len(by_league))

    for (league, country), league_fixtures in by_league.items():
        # Fit ZINB + load Elo once for the whole league
        hist_matches = await _load_history(db, league, country)
        zinb_model = ZINBMarketsModel()
        if len(hist_matches) >= _MIN_HISTORY:
            zinb_model.fit(hist_matches)
            logger.debug("ensemble_service: ZINB fitted for '%s' (%d matches)", league, len(hist_matches))
        elo = await _load_elo_for_league(db, league, country, hist_matches)

        for fixture in league_fixtures:
            n = await _process_fixture(
                db, fixture, snapshot_at, horizon, calibrators, zinb_model, elo
            )
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
    calibrators: dict[str, str] | None = None,
    zinb_model: ZINBMarketsModel | None = None,
    elo: "EloSystem | None" = None,
) -> dict[str, int]:
    home = fixture.home_team
    away = fixture.away_team

    # 1. ZINB probabilities (model already fitted per league)
    if zinb_model is not None and zinb_model._model.fitted:
        zinb_probs = zinb_model.predict_market_probs(home, away)
        lambda_home, lambda_away = zinb_model.predict_lambdas(home, away)
    else:
        zinb_probs = {}
        lambda_home, lambda_away = None, None

    # 2. Elo 1X2 probabilities (system already loaded/fitted per league)
    if elo is not None:
        elo_home_rating = elo.get_rating(home)
        elo_away_rating = elo.get_rating(away)
        elo_1x2 = elo.predict_1x2(home, away)
    else:
        elo_home_rating, elo_away_rating, elo_1x2 = None, None, None

    # 4+5. Load MarketSnapshot rows; run Bayesian engine to get probs + best odds
    bayesian_probs, market_odds = await _load_bayesian_and_odds(db, fixture)

    # 6. XGBoost meta-learner (active only when models exist on disk)
    try:
        from app.engines.xgboost_model import get_xgb_ensemble
        xgb_ens = get_xgb_ensemble()
        xgb_probs = xgb_ens.predict_all(
            zinb_probs=zinb_probs,
            bayesian_probs=bayesian_probs,
            elo_1x2=elo_1x2,
            market_odds=market_odds,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            elo_home=elo_home_rating,
            elo_away=elo_away_rating,
        ) if any(m.is_fitted for m in xgb_ens._models.values()) else None
    except Exception:
        xgb_probs = None

    # 7. Run ensemble
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
        xgb_probs=xgb_probs,
    )

    # 7. Archive ForecastSnapshot rows
    counts = {"total": 0, "signals": 0, "no_signals": 0}
    for r in results:
        knots = (calibrators or {}).get(r.market)
        cal_prob = apply_calibration_knots(knots, r.ensemble_prob) if knots else None

        snap = ForecastSnapshot(
            fixture_id=fixture.id,
            historical_fixture_id=None,
            snapshot_at=snapshot_at,
            horizon=horizon,
            market=r.market,
            zinb_prob=r.zinb_prob,
            bayesian_prob=r.bayesian_prob,
            elo_prob=r.elo_prob,
            xgb_prob=r.xgb_prob,
            ensemble_prob=r.ensemble_prob,
            calibrated_prob=cal_prob,
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


async def _load_elo_for_league(
    db: AsyncSession,
    league: str,
    country: str,
    hist_matches: list[dict],
) -> "EloSystem | None":
    """
    Load or fit an EloSystem for an entire league, to be shared across all
    fixtures in that league within a single sync run.

    Returns None if neither DB ratings nor hist_matches are available.
    """
    result = await db.execute(
        select(EloRating).where(EloRating.league == league).order_by(EloRating.season.desc())
    )
    stored = result.scalars().all()

    elo = EloSystem()
    if stored:
        elo.load_records([
            {
                "team_name": r.team_name,
                "rating": r.rating,
                "n_matches": r.n_matches,
                "last_match_date": r.last_match_date,
            }
            for r in stored
        ])
        return elo

    if hist_matches:
        elo.fit(hist_matches)
        await _persist_elo(db, elo, league, country)
        return elo

    return None


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


async def _load_bayesian_and_odds(
    db: AsyncSession,
    fixture: "Fixture",
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Run the Bayesian engine on MarketSnapshot rows for a live fixture, then
    augment with first-half implied probabilities from 1H bookmaker lines.
    Returns (bayesian_probs, market_odds) dicts keyed by PHASE1A_MARKETS market names.
    Falls back to ({}, {}) gracefully if no snapshot data exists.
    """
    from app.engines import bayesian as bay_engine

    snap_result = await db.execute(
        select(MarketSnapshot).where(MarketSnapshot.fixture_id == fixture.id)
    )
    raw_snaps = snap_result.scalars().all()
    if not raw_snaps:
        return {}, {}

    snaps = latest_snapshots(list(raw_snaps))

    bay_result = bay_engine.analyse_fixture(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        league=fixture.league or "",
        country=fixture.country or "",
        cs_by_bookie=build_cs_by_bookie(snaps),
        goals_ou=build_goals_ou(snaps),
        btts={},
        match_winner=build_match_winner(snaps),
        double_chance=build_double_chance(snaps),
        home_totals=build_home_totals(snaps),
        away_totals=build_away_totals(snaps),
        win_to_nil_home=build_win_to_nil_home(snaps),
        win_to_nil_away=build_win_to_nil_away(snaps),
        exact_goals=build_exact_goals(snaps),
        all_markets=True,
    )

    bayesian_probs: dict[str, float] = {}
    market_odds: dict[str, float] = {}
    for r in bay_result.market_results:
        if r.derived_prob and 0 < r.derived_prob < 1:
            bayesian_probs[r.market] = r.derived_prob
        if r.best_actual_odd and r.best_actual_odd > 1.0:
            market_odds[r.market] = r.best_actual_odd

    # Phase 1B: derive first-half implied probs from 1H market odds.
    # Bookmaker over/under lines give a two-way market; removing the overround
    # yields fair probabilities that serve as the "bayesian" component for 1H markets.
    def _implied_probs_from_ou(ou_odds: dict, targets: dict[str, tuple[str, str]]) -> None:
        for market_key, (target_sel, comp_sel) in targets.items():
            probs_sum = 0.0
            probs_count = 0
            best_bk_odds: float | None = None
            for bk_odds in ou_odds.values():
                t_o = bk_odds.get(target_sel)
                c_o = bk_odds.get(comp_sel)
                if t_o and c_o and t_o > 1.0 and c_o > 1.0:
                    overround = 1.0 / t_o + 1.0 / c_o
                    if overround > 0:
                        probs_sum += (1.0 / t_o) / overround
                        probs_count += 1
                        if best_bk_odds is None or t_o > best_bk_odds:
                            best_bk_odds = t_o
            if probs_count > 0:
                bayesian_probs[market_key] = round(probs_sum / probs_count, 6)
            if best_bk_odds is not None:
                market_odds[market_key] = best_bk_odds

    _implied_probs_from_ou(build_goals_first_half(snaps), {
        "1H Over 0.5":  ("Over 0.5",  "Under 0.5"),
        "1H Over 1.5":  ("Over 1.5",  "Under 1.5"),
        "1H Under 1.5": ("Under 1.5", "Over 1.5"),
    })

    _implied_probs_from_ou(build_goals_second_half(snaps), {
        "2H Over 0.5":  ("Over 0.5",  "Under 0.5"),
        "2H Over 1.5":  ("Over 1.5",  "Under 1.5"),
        "2H Under 1.5": ("Under 1.5", "Over 1.5"),
    })

    return bayesian_probs, market_odds
