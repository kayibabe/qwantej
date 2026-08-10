"""
calibration_service.py — Phase 1C learning loop.

Two public entry points:

  backfill_and_settle(db, cutoff)
      Runs the ensemble on every HistoricalFixture in the holdout window
      (match_date >= cutoff) and writes ForecastSnapshot rows with outcome
      and brier_score already filled — no separate settlement step needed
      because the true result is known at backfill time.

      Models are fitted per-league on matches before the cutoff, then applied
      to each holdout match in chronological order (Elo is updated after each
      prediction to simulate real-time ratings).

  run_calibration(db, min_samples, model_version)
      Loads all settled ForecastSnapshot rows (outcome IN ('WIN','LOSS')),
      groups by market, fits per-market isotonic regression, writes
      CalibrationRecord rows, and deactivates previous records for the same
      (market, model_version) pair.

Helper:
  apply_calibration_knots(knots_json, prob) -> float
      Used by ensemble_service.py at prediction time to convert raw
      ensemble_prob to calibrated_prob without hitting the database.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ensemble import EnsembleEngine, MODEL_VERSION
from app.engines.elo import EloSystem
from app.engines.zinb_markets import ZINBMarketsModel, PHASE1A_MARKETS
from app.models.calibration_record import CalibrationRecord
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.historical_fixture import HistoricalFixture

logger = logging.getLogger(__name__)

# Matches before this date are training data; on/after are calibration holdout.
_TRAIN_CUTOFF = date(2022, 7, 1)

_MIN_TRAIN = 20       # minimum training matches before fitting models for a league
_MIN_SAMPLES = 50     # minimum settled snapshots per market for calibration


# ---------------------------------------------------------------------------
# Market outcome lookup
# ---------------------------------------------------------------------------

def _market_outcome(hf: HistoricalFixture, market: str) -> Optional[int]:
    """Return 1 (outcome hit), 0 (miss), or None (data missing)."""
    if market == "Over 1.5":
        return int(hf.over_1_5) if hf.over_1_5 is not None else None
    if market == "Over 2.5":
        return int(hf.over_2_5) if hf.over_2_5 is not None else None
    if market == "Under 2.5":
        return int(hf.under_2_5) if hf.under_2_5 is not None else None
    if market == "Under 3.5":
        return int(hf.under_3_5) if hf.under_3_5 is not None else None
    if market == "BTTS Yes":
        return int(hf.btts) if hf.btts is not None else None
    if market == "1X (Home or Draw)":
        return int(hf.result in ("H", "D")) if hf.result else None
    if market == "X2 (Draw or Away)":
        return int(hf.result in ("D", "A")) if hf.result else None
    if market == "Home Over 0.5":
        return int(hf.home_goals >= 1) if hf.home_goals is not None else None
    if market == "Away Over 0.5":
        return int(hf.away_goals >= 1) if hf.away_goals is not None else None
    # Phase 2 — first-half markets
    if market in ("1H Over 0.5", "1H Over 1.5", "1H Under 1.5"):
        if hf.home_goals_ht is None or hf.away_goals_ht is None:
            return None
        ht_total = hf.home_goals_ht + hf.away_goals_ht
        if market == "1H Over 0.5":
            return int(ht_total >= 1)
        if market == "1H Over 1.5":
            return int(ht_total >= 2)
        if market == "1H Under 1.5":
            return int(ht_total <= 1)
    return None


# Pre-match odds fields available in HistoricalFixture for value-edge calculation
_HIST_ODDS_MAP: dict[str, str] = {
    "Over 1.5":  "odds_over_1_5",
    "Over 2.5":  "odds_over_2_5",
    "Under 2.5": "odds_under_2_5",
    "Under 3.5": "odds_under_3_5",
    "BTTS Yes":  "odds_btts_yes",
}


def _bayesian_probs_from_hist(hf: HistoricalFixture) -> dict[str, float]:
    """Compute vig-removed implied probabilities from historical pre-match odds.

    Over/Under markets: 2-outcome normalisation (over + under = 1).
    1X2 markets: 3-outcome normalisation using home/draw/away odds.
    Returns only markets for which both sides of the market are available.
    """
    probs: dict[str, float] = {}

    # Over/Under pairs — vig removed via 2-outcome normalisation
    pairs = [
        ("Over 1.5",  "odds_over_1_5",  "odds_under_1_5"),
        ("Over 2.5",  "odds_over_2_5",  "odds_under_2_5"),
        ("Under 2.5", "odds_under_2_5", "odds_over_2_5"),
        ("Under 3.5", "odds_under_3_5", "odds_over_3_5"),
    ]
    for market, self_field, other_field in pairs:
        o_self  = getattr(hf, self_field,  None)
        o_other = getattr(hf, other_field, None)
        if o_self and o_other and o_self > 1.0 and o_other > 1.0:
            total = 1.0 / o_self + 1.0 / o_other
            probs[market] = round((1.0 / o_self) / total, 6)

    # BTTS — 2-outcome normalisation
    if hf.odds_btts_yes and hf.odds_btts_no and hf.odds_btts_yes > 1.0 and hf.odds_btts_no > 1.0:
        total = 1.0 / hf.odds_btts_yes + 1.0 / hf.odds_btts_no
        probs["BTTS Yes"] = round((1.0 / hf.odds_btts_yes) / total, 6)

    # 1X2 — 3-outcome normalisation for double-chance markets
    h = hf.odds_home_win
    d = hf.odds_draw
    a = hf.odds_away_win
    if h and d and a and h > 1.0 and d > 1.0 and a > 1.0:
        overround = 1.0 / h + 1.0 / d + 1.0 / a
        probs["1X (Home or Draw)"] = round((1.0 / h + 1.0 / d) / overround, 6)
        probs["X2 (Draw or Away)"] = round((1.0 / d + 1.0 / a) / overround, 6)

    return probs


def _market_odds_from_hist(hf: HistoricalFixture) -> dict[str, float]:
    """Build the market_odds dict for the ensemble engine.

    For goals markets, uses the FD.co.uk closing odds directly.
    For 1X/X2, derives fair odds from the 1X2 market (vig-free implied prob).
    This is an approximation — actual 1X/X2 bookmaker prices carry a separate
    margin, so value edges computed here are slightly inflated versus reality.
    The approximation is acceptable for calibration purposes.
    """
    odds: dict[str, float] = {}
    for market, field in _HIST_ODDS_MAP.items():
        v = getattr(hf, field, None)
        if v is not None and v > 1.0:
            odds[market] = float(v)

    # Derive 1X and X2 market odds from vig-free implied probability
    h = hf.odds_home_win
    d = hf.odds_draw
    a = hf.odds_away_win
    if h and d and a and h > 1.0 and d > 1.0 and a > 1.0:
        overround = 1.0 / h + 1.0 / d + 1.0 / a
        p_1x = (1.0 / h + 1.0 / d) / overround
        p_x2 = (1.0 / d + 1.0 / a) / overround
        if p_1x > 0:
            odds["1X (Home or Draw)"] = round(1.0 / p_1x, 4)
        if p_x2 > 0:
            odds["X2 (Draw or Away)"] = round(1.0 / p_x2, 4)

    return odds


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

async def backfill_and_settle(
    db: AsyncSession,
    cutoff: date = _TRAIN_CUTOFF,
    force_refresh: bool = False,
) -> dict[str, int]:
    """
    Run the ensemble on all holdout HistoricalFixtures and write settled
    ForecastSnapshot rows. Skips fixtures that already have a snapshot unless
    force_refresh=True, which deletes and re-computes all historical snapshots.

    Returns {"leagues_processed", "fixtures_processed", "snapshots_written", "skipped"}.
    """
    summary = {
        "leagues_processed": 0,
        "fixtures_processed": 0,
        "snapshots_written": 0,
        "skipped": 0,
    }

    if force_refresh:
        from sqlalchemy import delete as _delete
        await db.execute(
            _delete(ForecastSnapshot).where(
                ForecastSnapshot.historical_fixture_id.isnot(None)
            )
        )
        await db.commit()
        logger.info("calibration: force_refresh — deleted existing historical snapshots")

    # --- Fetch all distinct leagues in the warehouse -----------------------
    from sqlalchemy import text as _text
    rows = await db.execute(
        _text("SELECT DISTINCT league, country FROM historical_fixtures ORDER BY league")
    )
    leagues = rows.all()
    logger.info("calibration: backfilling %d leagues (cutoff=%s)", len(leagues), cutoff)

    for league, country in leagues:
        counts = await _backfill_league(db, league, country, cutoff)
        summary["leagues_processed"] += 1
        summary["fixtures_processed"] += counts["fixtures"]
        summary["snapshots_written"] += counts["written"]
        summary["skipped"] += counts["skipped"]

    logger.info("calibration: backfill complete — %s", summary)
    return summary


async def _backfill_league(
    db: AsyncSession,
    league: str,
    country: str,
    cutoff: date,
) -> dict[str, int]:
    # Keepalive ping: ZINB/Elo fitting is CPU-bound and can idle the connection
    # long enough for asyncpg to drop it. A SELECT 1 before the real query
    # ensures the connection is alive before we start.
    from sqlalchemy import text as _text_ping
    await db.execute(_text_ping("SELECT 1"))

    # Load all completed fixtures for this league ordered by date
    result = await db.execute(
        select(HistoricalFixture).where(
            and_(
                HistoricalFixture.league == league,
                HistoricalFixture.home_goals.is_not(None),
                HistoricalFixture.away_goals.is_not(None),
            )
        ).order_by(HistoricalFixture.match_date.asc())
    )
    all_fixtures: list[HistoricalFixture] = list(result.scalars().all())

    train = [hf for hf in all_fixtures if hf.match_date < cutoff]
    holdout = [hf for hf in all_fixtures if hf.match_date >= cutoff]

    if len(train) < _MIN_TRAIN or not holdout:
        return {"fixtures": 0, "written": 0, "skipped": 0}

    # Commit before fitting so the connection is NOT "idle in transaction"
    # during CPU-bound scipy work.
    await db.commit()

    # Run synchronous scipy/numpy fitting in a thread-pool executor so the
    # asyncio event loop is NOT blocked during model fitting.  A blocked event
    # loop prevents asyncpg's keepalive tasks from running, causing the Fly.io
    # Postgres proxy to RST the TCP connection after a few seconds of silence.
    import asyncio as _asyncio
    loop = _asyncio.get_event_loop()

    zinb = ZINBMarketsModel()
    train_dicts = _to_dicts(train)
    await loop.run_in_executor(None, zinb.fit, train_dicts)

    elo = EloSystem()
    await loop.run_in_executor(None, elo.fit, train_dicts)

    # Fetch already-backfilled historical_fixture_ids to skip
    existing_ids_result = await db.execute(
        select(ForecastSnapshot.historical_fixture_id).where(
            ForecastSnapshot.historical_fixture_id.in_([hf.id for hf in holdout])
        ).distinct()
    )
    already_done: set[int] = {r for (r,) in existing_ids_result.all()}

    engine = EnsembleEngine()
    written = skipped = 0
    snapshot_at = datetime.now(tz=timezone.utc)
    # Commit every N fixtures to keep INSERT batches small.
    # 100 fixtures × 9 markets = 900 rows = 441KB SQL — too large for the
    # Fly.io Postgres proxy which drops connections on oversized packets.
    # 5 fixtures × 9 markets = 45 rows ≈ 22KB — safely within limits.
    _BATCH_SIZE = 5
    batch_count = 0

    for hf in holdout:
        if hf.id in already_done:
            skipped += 1
            # Still update Elo so subsequent predictions are accurate
            elo.update(
                hf.home_team, hf.away_team,
                hf.home_goals, hf.away_goals,
                hf.match_date.isoformat(),
            )
            continue

        # Get Elo prediction BEFORE updating with this match's result
        elo_home = elo.get_rating(hf.home_team)
        elo_away = elo.get_rating(hf.away_team)
        elo_1x2 = elo.predict_1x2(hf.home_team, hf.away_team)

        zinb_probs = zinb.predict_market_probs(hf.home_team, hf.away_team)
        lambda_home, lambda_away = (
            zinb.predict_lambdas(hf.home_team, hf.away_team)
            if zinb._model.fitted else (None, None)
        )

        bayesian_probs = _bayesian_probs_from_hist(hf)
        market_odds = _market_odds_from_hist(hf)

        results = engine.compute(
            zinb_probs=zinb_probs,
            bayesian_probs=bayesian_probs,
            elo_1x2=elo_1x2,
            market_odds=market_odds,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            elo_home=elo_home,
            elo_away=elo_away,
        )

        for r in results:
            outcome_int = _market_outcome(hf, r.market)
            if outcome_int is None:
                continue  # skip markets with missing result data

            brier = round((r.ensemble_prob - outcome_int) ** 2, 6)
            outcome_str = "WIN" if outcome_int == 1 else "LOSS"

            snap = ForecastSnapshot(
                fixture_id=None,
                historical_fixture_id=hf.id,
                snapshot_at=snapshot_at,
                horizon="backfill",
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
                outcome=outcome_str,
                actual_home_goals=hf.home_goals,
                actual_away_goals=hf.away_goals,
                settled_at=datetime.combine(hf.match_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ),
                brier_score=brier,
                model_version=r.model_version,
            )
            db.add(snap)
            written += 1

        # Update Elo ratings with actual result
        elo.update(
            hf.home_team, hf.away_team,
            hf.home_goals, hf.away_goals,
            hf.match_date.isoformat(),
        )

        batch_count += 1
        if batch_count % _BATCH_SIZE == 0:
            await db.commit()

    await db.commit()
    return {"fixtures": len(holdout), "written": written, "skipped": skipped}


def _to_dicts(fixtures: list[HistoricalFixture]) -> list[dict]:
    return [
        {
            "home_team": hf.home_team,
            "away_team": hf.away_team,
            "home_goals": hf.home_goals,
            "away_goals": hf.away_goals,
            "match_date": hf.match_date.isoformat() if hf.match_date else "",
        }
        for hf in fixtures
    ]


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

async def run_calibration(
    db: AsyncSession,
    min_samples: int = _MIN_SAMPLES,
    model_version: str = MODEL_VERSION,
) -> list[CalibrationRecord]:
    """
    Fit per-market isotonic calibrators on all settled ForecastSnapshot rows.
    Writes new CalibrationRecord rows and deactivates previous ones.
    Returns the list of new records.
    """
    # Load all settled snapshots (outcome set)
    result = await db.execute(
        select(
            ForecastSnapshot.market,
            ForecastSnapshot.ensemble_prob,
            ForecastSnapshot.outcome,
        ).where(
            ForecastSnapshot.outcome.in_(["WIN", "LOSS"]),
            ForecastSnapshot.model_version == model_version,
        )
    )
    rows = result.all()

    if not rows:
        logger.warning("calibration: no settled snapshots found — skipping")
        return []

    # Group by market
    by_market: dict[str, list[tuple[float, int]]] = {}
    for market, prob, outcome in rows:
        if prob is None:
            continue
        binary = 1 if outcome == "WIN" else 0
        by_market.setdefault(market, []).append((float(prob), binary))

    new_records: list[CalibrationRecord] = []
    now = datetime.now(tz=timezone.utc)

    for market, pairs in by_market.items():
        if len(pairs) < min_samples:
            logger.info("calibration: %s — only %d samples, skipping", market, len(pairs))
            continue

        probs = np.array([p for p, _ in pairs])
        outcomes = np.array([o for _, o in pairs], dtype=float)

        # Sort by probability (required for isotonic regression)
        sort_idx = np.argsort(probs)
        x_sorted = probs[sort_idx]
        y_sorted = outcomes[sort_idx]

        # Fit isotonic regression via PAV (scipy >= 1.12)
        from scipy.optimize import isotonic_regression as _pav
        res = _pav(y_sorted, increasing=True)
        y_iso = res.x

        # Brier scores
        raw_brier = float(np.mean((probs - outcomes) ** 2))
        cal_probs = np.interp(probs, x_sorted, y_iso)
        calibrated_brier = float(np.mean((cal_probs - outcomes) ** 2))

        knots_json = json.dumps({
            "x": x_sorted.tolist(),
            "y": y_iso.tolist(),
        })

        # Deactivate previous active records for this market+version
        await db.execute(
            update(CalibrationRecord)
            .where(
                CalibrationRecord.market == market,
                CalibrationRecord.model_version == model_version,
                CalibrationRecord.is_active.is_(True),
            )
            .values(is_active=False)
        )

        rec = CalibrationRecord(
            market=market,
            model_version=model_version,
            n_samples=len(pairs),
            raw_brier=raw_brier,
            calibrated_brier=calibrated_brier,
            brier_improvement=round(raw_brier - calibrated_brier, 6),
            calibration_knots_json=knots_json,
            is_active=True,
            computed_at=now,
        )
        db.add(rec)
        new_records.append(rec)

        logger.info(
            "calibration: %s — n=%d  raw_brier=%.4f  cal_brier=%.4f  improvement=%.4f",
            market, len(pairs), raw_brier, calibrated_brier, raw_brier - calibrated_brier,
        )

    await db.commit()
    logger.info("calibration: wrote %d CalibrationRecord rows", len(new_records))
    return new_records


# ---------------------------------------------------------------------------
# Prediction-time helper
# ---------------------------------------------------------------------------

def apply_calibration_knots(knots_json: str, prob: float) -> float:
    """
    Apply serialised isotonic calibration knots to a raw probability.
    Uses linear interpolation between knot points (numpy.interp).
    Returns prob unchanged if knots_json is empty or malformed.
    """
    try:
        state = json.loads(knots_json)
        return float(np.interp(prob, state["x"], state["y"]))
    except Exception:
        return prob


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _run(cutoff_str: Optional[str] = None) -> None:
    import argparse
    from app.core.database import AsyncSessionLocal

    cutoff = date.fromisoformat(cutoff_str) if cutoff_str else _TRAIN_CUTOFF

    async with AsyncSessionLocal() as db:
        print(f"[1/2] Backfilling snapshots (holdout >= {cutoff}) ...")
        counts = await backfill_and_settle(db, cutoff=cutoff)
        print(f"      {counts}")

        print("[2/2] Running calibration ...")
        records = await run_calibration(db)
        for rec in records:
            print(
                f"      {rec.market:<30}  n={rec.n_samples:<6}"
                f"  Brier {rec.raw_brier:.4f} → {rec.calibrated_brier:.4f}"
                f"  improvement={rec.brier_improvement:+.4f}"
            )
        if not records:
            print("      (no markets had enough samples)")


if __name__ == "__main__":
    import asyncio, sys
    cutoff_arg = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(_run(cutoff_arg))
