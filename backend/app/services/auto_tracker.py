"""
auto_tracker.py — Backend auto-tracking of system signals and ACCAs.

Creates TrackedBet rows (user_id=None) for every qualifying signal on a date.
Idempotent: existing rows are skipped.  Called from sync_and_compute() so
auto-tracking runs every sync cycle regardless of whether anyone visits the
Signals page.

Qualifying signals (everything served to subscribers):
  - Any signal with is_candidate=False and dual_agreement != "Contradiction"
  - Suppression guards applied (DISABLED_LEAGUES, OVER_GOALS_SUPPRESSED_LEAGUES,
    women's league filters, HO05_DATA_POOR_COUNTRIES, DUAL_HIGH_ODDS_CEILING)

ACCA auto-tracking (auto_track_acca_signals):
  - Builds a signal-model ACCA from all qualifying candidates each sync cycle.
  - On subsequent calls for the same day, only fixtures NOT already in an
    earlier system_acca ticket are eligible — guaranteeing zero leg overlap
    across multiple ACCA tickets for the same date.
  - Minimum 2 unused candidates required; target odds 4.0, fallback 3.5, 3.0.
  - Defers to advisor-path ACCA (acca_leg_system) when leg rows already exist.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Signal, Fixture, TrackedBet
from app.models.learning_proposal import LearningProposal
from app.models.user import User as _User  # noqa: F401 — registers users table in SA metadata
from app.core.config import (
    DUAL_HIGH_ODDS_CEILING, WOMEN_LEAGUE_KEYWORDS,
    WOMEN_OVER_SUPPRESSED_MARKETS, HO05_DATA_POOR_COUNTRIES,
    DISABLED_LEAGUES, DISABLED_MARKETS, OVER_GOALS_SUPPRESSED_LEAGUES,
    OVER25_SUPPRESSED_TIERS, MARKET_MIN_ODDS, HALVED_STAKE_LEAGUES,
    COPA_HO05_SUPPRESSED_LEAGUES, AWAY_GOALS_SUPPRESSED_LEAGUES,
    is_womens_fixture, ZINB_GOALS_MIN_ODDS,
    HO05_ALL_TIERS_SUPPRESSED_COUNTRIES, U35_DATA_POOR_COUNTRIES,
    UEFA_CLUB_COMP_KEYWORDS, is_grade_c_ceiling_exception,
)
from app.services.acca_builder import (
    build_acca_candidates, build_accumulator, _ACCA_WIN_PROB_FLOOR,
)

logger = logging.getLogger("Qwantej.auto_tracker")

FLAT_STAKE = 50_000.0


async def _load_kelly_multipliers(db: AsyncSession) -> dict[str, float]:
    """
    Returns active kelly_fraction_adj multipliers keyed by dual_confidence target.
    E.g. {"High": 0.5} means Both+High stakes are halved before tracking.
    Falls back to {} (no adjustment) on any error.
    """
    try:
        result = await db.execute(
            select(LearningProposal).where(
                LearningProposal.change_type == "kelly_fraction_adj",
                LearningProposal.is_active == True,  # noqa: E712
            )
        )
        proposals = result.scalars().all()
        return {
            p.target: float(p.proposed_value)
            for p in proposals
            if p.proposed_value is not None and 0.1 <= float(p.proposed_value) <= 1.0
        }
    except Exception:
        logger.warning("_load_kelly_multipliers: could not load proposals — using 1.0×")
        return {}


def _grade(q: float | None) -> str | None:
    # Thresholds recalibrated 2026-07-02 for the probability-based quality scale
    # (quality ≈ prob × tier/bookmaker/confidence factors, typically 0.2–0.8;
    # the old 0.035–0.08 cutoffs matched the retired EV-based scale).
    if q is None:
        return None
    if q >= 0.60: return "A"
    if q >= 0.45: return "B"
    if q >= 0.30: return "C"
    return "D"


async def auto_track_date(db: AsyncSession, run_date: date) -> int:
    """
    Create system TrackedBet rows for all qualifying signals on run_date.
    Tracks every signal served to subscribers: is_candidate=False and not a
    Contradiction (engines actively disagree → no bet).
    Returns count of newly inserted bets.
    """
    # Load all non-candidate, non-contradiction signals for this date
    rows = list(
        (await db.execute(
            select(Signal, Fixture)
            .join(Fixture, Signal.fixture_id == Fixture.id)
            .where(Fixture.event_date == run_date)
            .where(Signal.is_candidate == False)  # noqa: E712
            .where(Signal.dual_agreement != "Contradiction")
        )).all()
    )

    if not rows:
        return 0

    # Load active kelly_fraction_adj multipliers from learning proposals.
    kelly_mults = await _load_kelly_multipliers(db)

    # Load existing bets for this date to avoid duplicates.
    # Check on (fixture_id, market_type) only — bookmaker varies between the
    # old per-user strategy-tracker rows and the new system_auto rows, so
    # using bookmaker in the key would miss those collisions.
    existing_rows = list(
        (await db.execute(
            select(TrackedBet.fixture_id, TrackedBet.market_type)
            .where(TrackedBet.event_date == run_date)
        )).all()
    )
    existing_keys: set[tuple] = {
        (r.fixture_id, r.market_type) for r in existing_rows
    }
    # Also include NULL-event_date rows (fixture lookup failed during ingestion) so
    # a subsequent sync with a resolved date doesn't double-track the same pick.
    null_date_rows = list(
        (await db.execute(
            select(TrackedBet.fixture_id, TrackedBet.market_type)
            .where(TrackedBet.event_date.is_(None))
            .where(TrackedBet.fixture_id.isnot(None))
        )).all()
    )
    existing_keys |= {(r.fixture_id, r.market_type) for r in null_date_rows}

    rows.sort(key=lambda r: (r[0].dual_quality_score or 0.0), reverse=True)

    inserted = 0
    for signal, fixture in rows:

        bookmaker = signal.bayesian_bookmaker or "Best Available"
        key = (signal.fixture_id, signal.market)
        if key in existing_keys:
            continue

        # Hybrid B signals carry their own qualifying filters, league blacklists,
        # odds tiers, and MWK staking — legacy market/odds gates below are bypassed
        # for them (guarded with `not is_hybrid`).
        is_hybrid = signal.poisson_rule_key == "hybrid_b"
        # ZINB goals signals (zinb_o15, zinb_o25, zinb_u25, zinb_u35) share Hybrid B
        # stake sizing and bypass the old dual-engine odds/confidence gates.
        is_zinb_goals = (signal.poisson_rule_key or "").startswith("zinb_")

        # Defense-in-depth: skip disabled markets and leagues.
        # signal_engine and router already filter these, but old signals in the
        # DB (generated before a market/league was retired) can still reach this loop.
        # Hybrid B signals bypass this gate — the engine owns its own market list
        # (X2 + Away O0.5) and should never be blocked by the legacy disabled set.
        if not is_hybrid and not is_zinb_goals and signal.market in DISABLED_MARKETS:
            continue
        league_lower = (fixture.league or "").lower().strip()
        if league_lower in DISABLED_LEAGUES or "friendlies" in league_lower:
            continue
        if not is_hybrid and signal.market in {"Home Over 0.5", "Away Over 0.5", "Over 1.5", "Over 2.5"}:
            if any(k in league_lower for k in OVER_GOALS_SUPPRESSED_LEAGUES):
                continue
        if signal.market == "Over 2.5" and fixture.league_tier in OVER25_SUPPRESSED_TIERS:
            continue

        odds = signal.bayesian_best_odd
        if not odds or odds <= 1.01:
            prob = signal.poisson_prob or signal.bayesian_prob
            if prob and 0.0 < prob < 1.0:
                odds = round(1.0 / prob, 3)
            else:
                continue

        # Skip signals below the minimum odds floor — parity with router serving gate.
        # Hybrid B and ZINB goals exempt: they use their own stake/odds tier logic.
        min_odds_floor = MARKET_MIN_ODDS.get(signal.market)
        if not is_hybrid and not is_zinb_goals and min_odds_floor is not None and odds < min_odds_floor:
            continue

        # ZINB goals: apply per-market minimum odds gates (calibrated floors).
        # Parity with the serving-time filter in routers/signals.py.
        if is_zinb_goals:
            zinb_floor = ZINB_GOALS_MIN_ODDS.get(signal.poisson_rule_key or "")
            if zinb_floor is not None and odds < zinb_floor:
                continue

        # Skip Both+High picks whose odds exceed the serving-time ceiling —
        # consistent with what the router shows subscribers. Hybrid B exempt.
        # Grade C exception: odds >= 2.50 + quality >= 0.30 bypasses the ceiling
        # (5W/0L backfill at Tier 1/2).
        ceiling = DUAL_HIGH_ODDS_CEILING.get(signal.market)
        if (
            not is_hybrid
            and ceiling is not None
            and signal.dual_confidence == "High"
            and signal.dual_agreement == "Both"
            and odds >= ceiling
            and not is_grade_c_ceiling_exception(odds, signal.dual_quality_score)
        ):
            continue

        # Copa/cup gate: Home Over 0.5 suppressed in South American cup competitions.
        # Rotation/reserve line-ups + knockout incentives depress home-scoring rates.
        # Mirrors the serving-time gate in routers/signals.py.
        if (
            signal.market == "Home Over 0.5"
            and COPA_HO05_SUPPRESSED_LEAGUES
            and any(kw in league_lower for kw in COPA_HO05_SUPPRESSED_LEAGUES)
        ):
            continue

        # Away-goals suppression: primera b metropolitana and other leagues where
        # away-scoring model overestimates hit rate. Mirrors router serving gate.
        # Hybrid B exempt — the engine has its own league blacklists.
        if (
            not is_hybrid
            and signal.market in {"Away Over 0.5", "Away Over 1.5"}
            and AWAY_GOALS_SUPPRESSED_LEAGUES
            and any(kw in league_lower for kw in AWAY_GOALS_SUPPRESSED_LEAGUES)
        ):
            continue

        # Skip women's league over-goals picks — models calibrated on men's
        # football systematically overestimate scoring in women's fixtures.
        if (
            signal.market in WOMEN_OVER_SUPPRESSED_MARKETS
            and is_womens_fixture(fixture.league, fixture.home_team, fixture.away_team)
        ):
            continue

        # Skip Both+High Home Over 0.5 from data-poor countries at Tier 3.
        # Both engines can agree with high confidence on insufficient historical
        # data — the agreement reflects noise, not genuine edge.
        if (
            signal.market == "Home Over 0.5"
            and signal.dual_confidence == "High"
            and signal.dual_agreement == "Both"
            and (fixture.league_tier or 3) >= 3
            and (fixture.country or "").lower() in HO05_DATA_POOR_COUNTRIES
        ):
            continue

        # Home Over 0.5 suppressed for these countries at ALL tiers.
        # Australian state leagues are mis-classified as T1 by the API.
        # Aug-2026: St George Willawong 0-1 @ 1.51 (T1).
        if (
            signal.market == "Home Over 0.5"
            and (fixture.country or "").lower() in HO05_ALL_TIERS_SUPPRESSED_COUNTRIES
        ):
            continue

        # Under 3.5 suppressed for data-poor countries at any tier.
        # ZINB λ calibration is unreliable where historical match data is thin.
        # Aug-2026: Armenia 2-2 @ 1.19 (T1), Nicaragua 4-1 @ 1.36 (T3),
        # Faroe Islands 3-2 @ 1.30 (T2).
        if (
            signal.market == "Under 3.5"
            and (fixture.country or "").lower() in U35_DATA_POOR_COUNTRIES
        ):
            continue

        # Glicko gate: skip HO0.5 where the home team is a heavy underdog.
        # glicko_r_diff < -150 means the home side is outrated by >150 Glicko points —
        # home goals are structurally improbable regardless of lambda.
        # Aug-2026: Banik Ostrava vs Slavia Praha (diff=-180) 0-4.
        _glicko = signal.glicko_r_diff
        if signal.market == "Home Over 0.5" and _glicko is not None and _glicko < -150:
            continue

        # Tighter Glicko gate for UEFA club competitions: -100 vs the general -150.
        # Small-nation clubs in CL/EL/UECL qualifiers are structurally outclassed
        # in the -100 to -149 band the general gate misses.
        # Aug-2026: HB Torshavn (Faroe Islands) 0-3 vs Motherwell (UECL).
        if (
            signal.market == "Home Over 0.5"
            and _glicko is not None
            and _glicko < -100
            and any(kw in league_lower for kw in UEFA_CLUB_COMP_KEYWORDS)
        ):
            continue

        # BOS gate: stable/defensive fixture (bos_passed=True) contradicts any
        # Over-goals pick — the model flags low scoring but we'd be betting on goals.
        # Hybrid B exempt — it treats Stable as favourable (conditional blacklist
        # only fires on Unstable fixtures).
        _OVER_MARKETS = {"Home Over 0.5", "Away Over 0.5", "Over 1.5", "Over 2.5",
                         "Home Over 1.5", "Away Over 1.5"}
        if not is_hybrid and signal.bos_passed and signal.market in _OVER_MARKETS:
            continue

        # B-4 gate (mirrors router): Both+Medium only at 1.50–1.94 odds.
        # < 1.50: 53.8% WR — correct block. ≥ 1.95: thin sample, excluded pending data.
        # Full-data audit Jul-2026: 13 bets at 1.65–2.09 ran 69.2% WR — previously
        # blocked gate was wrong; ceiling raised to 1.95 to capture the viable range.
        # Hybrid B exempt — its MEDIUM tier is odds 1.25–1.39 by design.
        if (
            not is_hybrid
            and signal.dual_agreement == "Both"
            and signal.dual_confidence == "Medium"
            and not (1.50 <= (signal.bayesian_best_odd or 0.0) < 1.95)
        ):
            continue

        # Over 1.5 confidence gate: only track High-confidence signals.
        # Jul-2026 audit: Medium-confidence Over 1.5 at 1.30–1.56 odds lands as
        # structural negative EV — market no-vig (~67-77%) exceeds model prob
        # (55-70%). High confidence (≥0.70) gives the model a realistic chance of
        # beating the market. Medium Bayesian-Only Over 1.5 is not suppressed from
        # signal generation (it informs pattern detection), only from auto-tracking.
        # ZINB goals signals are exempt: their confidence tiers reflect lambda
        # thresholds, not the Bayesian/Poisson dual-engine confidence scale.
        if (
            signal.market == "Over 1.5"
            and signal.dual_confidence != "High"
            and not is_zinb_goals
        ):
            continue

        agreement = signal.dual_agreement or ""
        confidence = signal.dual_confidence or ""
        match_name = f"{fixture.home_team} vs {fixture.away_team}"

        if is_hybrid:
            # SKIP tier means Phase 5 form-demotion (or any rejection path) produced
            # a zero-stake result — never place a bet for these signals.
            if signal.stake_tier == "SKIP":
                continue
            source_rule_key   = "system_hybrid_b"
            source_rule_label = f"Hybrid B ({signal.stake_tier or 'LOW'})"
            # Hybrid B staking is deterministic (Phase 4/5 already applied
            # tier logic, bonus booster, and form adjustments) — use it as-is.
            # Guard against 0.0 (falsy) falling back to FLAT_STAKE.
            stake = float(signal.recommended_stake) if signal.recommended_stake else FLAT_STAKE
        elif is_zinb_goals:
            # ZINB goals signals carry deterministic Kelly-tier staking computed
            # in signal_engine.py — use recommended_stake directly.
            if signal.stake_tier == "SKIP" or not signal.recommended_stake:
                continue
            source_rule_key   = "system_zinb_goals"
            source_rule_label = f"ZINB Goals ({signal.stake_tier or 'MEDIUM'})"
            stake = float(signal.recommended_stake)
        else:
            if agreement == "Both" and confidence == "High":
                source_rule_key   = "system_dual"
                source_rule_label = "Dual Signal (High+Both)"
            elif agreement == "Both":
                source_rule_key   = "system_dual"
                source_rule_label = f"Dual Signal ({confidence or 'Medium'}+Both)"
            elif agreement == "Poisson Only":
                source_rule_key   = "system_auto"
                source_rule_label = "System Poisson Pick"
            elif agreement == "Bayesian Only":
                source_rule_key   = "system_auto"
                source_rule_label = "System Bayesian Pick"
            else:
                source_rule_key   = "system_auto"
                source_rule_label = "System Auto-Pick"

            # Apply active kelly_fraction_adj multiplier (from learning proposals).
            kelly_mult = kelly_mults.get(confidence, 1.0)
            # Halve stake for leagues confirmed to have smaller edge than modelled.
            if league_lower in HALVED_STAKE_LEAGUES:
                kelly_mult *= 0.5
            stake = round(FLAT_STAKE * kelly_mult)
            if stake != FLAT_STAKE:
                logger.debug(
                    "auto_track: stake for %s %s confidence = %.0f (%.2f× of %.0f)",
                    signal.market, confidence, stake, kelly_mult, FLAT_STAKE,
                )

        bet = TrackedBet(
            user_id=None,
            fixture_id=signal.fixture_id,
            bookmaker=bookmaker,
            event_date=fixture.event_date,
            match_name=match_name,
            league=fixture.league,
            market_type=signal.market,
            selection_name=signal.market,
            odds=odds,
            stake=stake,
            recommended_stake_pct=signal.dual_recommended_stake_pct,
            source_rule_key=source_rule_key,
            source_rule_label=source_rule_label,
            signal_grade=_grade(signal.dual_quality_score),
            dual_confidence=signal.dual_confidence,
            dual_agreement=signal.dual_agreement,
            # Hybrid B passive tracking: Home O0.5 odds at signal time (never bet)
            home_o05_odds_logged=getattr(signal, "home_o05_odds_logged", None),
            result_status="Pending",
        )
        db.add(bet)
        existing_keys.add(key)
        inserted += 1

    if inserted:
        await db.commit()
        logger.info("Auto-tracker: inserted %d system bets for %s", inserted, run_date)

    return inserted


_ACCA_TARGET_TIERS = [4.0, 3.5, 3.0]
_ACCA_MIN_CANDIDATES = 2


async def auto_track_acca_signals(
    db: AsyncSession,
    run_date: date,
) -> int:
    """
    Build and record a new system ACCA ticket from qualifying signal candidates,
    ensuring no fixture leg appears in any previously auto-tracked system_acca
    ticket for the same date.

    Defers entirely to the advisor-path ACCA (acca_leg_system / acca_advisory_system)
    when those tickets already exist for run_date — the presync and advisory-cache
    jobs take priority and this function is a fallback for dates they haven't covered.

    Returns count of new TrackedBet rows inserted (0 or 1 combined row).
    """
    # Defer to the advisor path if it has already run OR is scheduled to run.
    # Check 1: system_acca rows already exist (evening_extras job already ran).
    advisor_acca_count = await db.scalar(
        select(func.count()).select_from(TrackedBet).where(
            TrackedBet.event_date == run_date,
            TrackedBet.source_rule_key == "system_acca",
            TrackedBet.user_id.is_(None),
        )
    )
    if advisor_acca_count:
        logger.info(
            "Auto-ACCA %s: advisor-path ACCA ticket(s) already exist (%d row(s)) — skipping signal-model ticket",
            run_date, advisor_acca_count,
        )
        return 0

    # Check 2: advisory cache in system_settings has an accumulator for this date.
    # The 08:30 cache job will create acca_advisory_system rows later — we should
    # not create a competing system_acca now when the advisory is already planned.
    from sqlalchemy import text as _text
    import json as _json
    cache_row = await db.scalar(
        _text("SELECT value FROM system_settings WHERE key = :k"),
        {"k": f"advisory_cache_{run_date}"},
    )
    if cache_row:
        try:
            cached = _json.loads(cache_row)
            has_acca = bool(
                cached.get("accumulator") or
                cached.get("acca_of_the_day") or
                cached.get("accumulators") or
                cached.get("acca")
            )
            if has_acca:
                logger.info(
                    "Auto-ACCA %s: advisory cache has an accumulator — deferring to advisor path",
                    run_date,
                )
                return 0
        except Exception:
            pass  # malformed cache — fall through to signal-model

    # Collect fixture_ids already used in system_acca tickets for this date.
    existing_accas = list(
        (await db.execute(
            select(TrackedBet.notes)
            .where(
                TrackedBet.event_date == run_date,
                TrackedBet.source_rule_key == "system_acca",
                TrackedBet.user_id.is_(None),
            )
        )).scalars().all()
    )

    used_fixture_ids: set[int] = set()
    for notes_json in existing_accas:
        try:
            data = json.loads(notes_json or "{}")
            for leg in data.get("legs", []):
                fid = leg.get("fixture_id")
                if fid is not None:
                    used_fixture_ids.add(int(fid))
        except Exception:
            pass

    # Build candidate pool excluding already-used fixtures.
    candidates = await build_acca_candidates(
        db, run_date,
        exclude_fixture_ids=used_fixture_ids,
    )

    if len(candidates) < _ACCA_MIN_CANDIDATES:
        logger.info(
            "Auto-ACCA %s: only %d unused candidates (need %d) — skipping",
            run_date, len(candidates), _ACCA_MIN_CANDIDATES,
        )
        return 0

    # Try target tiers from highest to lowest; take the first that produces ≥2 legs.
    # max_legs=3 caps the ticket at 3 legs: a 4-leg ticket at 70%/leg has only 24%
    # win rate vs 34% for 3 legs — the extra leg destroys more EV than it adds odds.
    chosen: dict | None = None
    for tier in _ACCA_TARGET_TIERS:
        acca = build_accumulator(candidates, tier, max_legs=3)
        if acca["leg_count"] >= _ACCA_MIN_CANDIDATES:
            chosen = acca
            break

    if not chosen:
        logger.info("Auto-ACCA %s: could not build ≥2-leg ticket from %d candidates", run_date, len(candidates))
        return 0

    # Win probability floor: refuse tickets where compounded leg probabilities
    # fall below _ACCA_WIN_PROB_FLOOR.  A structurally poor-quality ticket
    # produces losing expectations regardless of combined odds target.
    if chosen["expected_win_probability"] < _ACCA_WIN_PROB_FLOOR:
        logger.info(
            "Auto-ACCA %s: expected win probability %.1f%% below %.0f%% floor — skipping",
            run_date,
            chosen["expected_win_probability"] * 100,
            _ACCA_WIN_PROB_FLOOR * 100,
        )
        return 0

    legs      = chosen["legs"]
    combined  = chosen["combined_odds"]
    leg_count = chosen["leg_count"]
    exp_win_p = chosen["expected_win_probability"]

    leg_summary = "\n".join(
        f"{i+1}. {leg.get('home_team','')} vs {leg.get('away_team','')} · "
        f"{leg.get('market','')} @ {float(leg.get('odd') or leg.get('fair_odds') or 0):.2f}"
        for i, leg in enumerate(legs)
    )

    # Dedup: don't insert if an identical leg set already exists (same fixture_ids in same order).
    fingerprint = ",".join(str(leg["fixture_id"]) for leg in legs)
    fp_tag      = f"system_acca|{fingerprint}"
    already     = await db.scalar(
        select(TrackedBet.id).where(
            TrackedBet.source_rule_key == "system_acca",
            TrackedBet.event_date == run_date,
            TrackedBet.user_id.is_(None),
            TrackedBet.selection_name == fp_tag,
        )
    )
    if already:
        logger.debug("Auto-ACCA %s: identical ticket already tracked — skipping", run_date)
        return 0

    db.add(TrackedBet(
        user_id=None,
        fixture_id=None,
        bookmaker="System Acca",
        event_date=run_date,
        match_name=f"AI Acca · {leg_count} leg{'s' if leg_count != 1 else ''}",
        league=None,
        market_type="Accumulator",
        selection_name=fp_tag,
        odds=combined,
        stake=FLAT_STAKE,
        source_rule_key="system_acca",
        source_rule_label="System ACCA",
        result_status="Pending",
        acca_ticket_id=fp_tag,
        notes=json.dumps({
            "legs":                    legs,
            "leg_summary":             leg_summary,
            "expected_win_probability": exp_win_p,
        }),
    ))

    await db.commit()
    logger.info(
        "Auto-ACCA %s: inserted %d-leg ticket @ %.2f combined odds (expected win %.1f%%)",
        run_date, leg_count, combined, exp_win_p * 100,
    )

    # Stamp acca_ticket_id on each leg's single-bet row so the self-learning
    # pipeline can correlate ACCA losses with individual leg types without
    # needing to parse notes JSON across thousands of rows.
    from sqlalchemy import text as _text
    stamped = False
    for leg in legs:
        fid = leg.get("fixture_id")
        mkt = leg.get("market")
        if fid and mkt:
            await db.execute(
                _text(
                    "UPDATE tracked_bets SET acca_ticket_id = :tid "
                    "WHERE fixture_id = :fid AND market_type = :mkt "
                    "AND user_id IS NULL AND acca_ticket_id IS NULL"
                ),
                {"tid": fp_tag, "fid": int(fid), "mkt": mkt},
            )
            stamped = True
    if stamped:
        await db.commit()

    return 1
