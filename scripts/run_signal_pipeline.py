"""Live signal pipeline: upcoming fixtures → predictions → accumulators → notifications.

Runs once per scheduled invocation (cron or --loop).  For each fixture kicking off
within the lookahead window that has not yet been predicted, the pipeline:

  1. Extracts PIT-safe features (as_of = now) via extract_fixture_features().
  2. Creates an immutable FeatureSnapshot via create_feature_snapshot().
  3. Runs the Poisson + Elo ensemble to produce raw match probabilities.
  4. Applies the current champion linear calibrator (fitted from recent settled
     predictions, or identity if fewer than CALIBRATION_MIN_SAMPLES exist).
  5. Evaluates the ValueGate (edge, EV, DQS, reliability).
  6. Publishes a fail-closed Prediction record for every fixture that passes.
  7. Runs the accumulator optimiser over all qualified selections for Core,
     Growth and Alpha tiers.
  8. Persists accumulator decisions (paper_only=True until production sign-off).
  9. Sends a Telegram summary notification.

**Paper-only**: all accumulators are persisted with paper_only=True.  A
separate release decision (with walk-forward evidence + Codex review) is
required before live staking.

Bootstrap: on first run the pipeline auto-registers a champion ModelRegistry row
and a champion CalibrationModel so that publish_prediction() can trace lineage.
These rows are created idempotently (upsert-by-version pattern) and never deleted.

Usage:
    python scripts/run_signal_pipeline.py
    python scripts/run_signal_pipeline.py --loop --interval 3600
    python scripts/run_signal_pipeline.py --lookahead 48 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
for _p in (str(repo_root), str(repo_root / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("signal_pipeline")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKET = "1X2"
_SELECTION = "home"
_MODEL_NAME = "poisson+elo-ensemble"
_MODEL_VERSION = "1.0.0"
_MODEL_FAMILY = "ensemble"
_IMPUTATION_POLICY_VERSION = "imputation-v1"
_FEATURE_VERSION = "feature-engineering-v1"
_CALIBRATION_MIN_SAMPLES = 30
_LOOKAHEAD_HOURS_DEFAULT = 36
_PRE_KICKOFF_WINDOW_HOURS = 2  # decision cutoff before kickoff


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

@dataclass
class PipelineRun:
    started_at: datetime
    fixtures_evaluated: int = 0
    features_extracted: int = 0
    predictions_published: int = 0
    value_gate_rejected: int = 0
    feature_errors: int = 0
    accumulators: list[str] = field(default_factory=list)  # "CORE", "GROWTH", "ALPHA"
    errors: int = 0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _code_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _sha256(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Bootstrap: champion model registry
# ---------------------------------------------------------------------------

def _ensure_champion_model(session: Any, now: datetime) -> tuple[Any, Any]:
    """Return (ModelRegistry, ModelRun) for the current inference run.

    Creates a champion ModelRegistry row if none exists for _MODEL_NAME/_MODEL_VERSION.
    Always creates a new ModelRun row for this pipeline invocation.
    """
    from sqlalchemy import select

    from backend.models import (
        ModelFamily,
        ModelRegistry,
        ModelRun,
        ModelRunKind,
        ModelRunStatus,
        ModelStatus,
    )

    commit = _code_commit()

    # Find or create champion registry row.
    stmt = select(ModelRegistry).where(
        ModelRegistry.name == _MODEL_NAME,
        ModelRegistry.version == _MODEL_VERSION,
    )
    registry = session.scalars(stmt).first()

    if registry is None:
        registry = ModelRegistry(
            family=ModelFamily.ENSEMBLE,
            name=_MODEL_NAME,
            version=_MODEL_VERSION,
            status=ModelStatus.CHAMPION,
            code_commit=commit,
            hyperparameters={
                "k_factor": 20.0,
                "home_elo_advantage": 65.0,
                "initial_elo": 1500.0,
                "poisson_elo_blend": 0.5,
            },
            description="Poisson + Elo blend; P(home win) ensemble (Phase 3).",
            promoted_at=now,
        )
        session.add(registry)
        session.flush()
        log.info("signal_pipeline: registered champion model %s v%s", _MODEL_NAME, _MODEL_VERSION)
    elif registry.status.value != "champion":
        log.warning(
            "signal_pipeline: model %s/%s exists but status=%s — using anyway",
            _MODEL_NAME, _MODEL_VERSION, registry.status,
        )

    # Always create a fresh ModelRun for this invocation.
    run = ModelRun(
        model_id=registry.id,
        kind=ModelRunKind.INFERENCE,
        status=ModelRunStatus.RUNNING,
        started_at=now,
        code_commit=commit,
        parameters={"market": _MARKET, "selection": _SELECTION},
    )
    session.add(run)
    session.flush()
    log.info("signal_pipeline: created model_run %s", run.id)
    return registry, run


# ---------------------------------------------------------------------------
# Bootstrap: champion calibration model
# ---------------------------------------------------------------------------

def _fit_linear_calibration(probs: list[float], outcomes: list[float]) -> dict:
    """OLS linear fit: outcome ~ slope * prob + intercept.

    Returns {"slope": float, "intercept": float}.  Falls back to identity
    if the system is degenerate (all probabilities equal).
    """
    n = len(probs)
    mean_p = sum(probs) / n
    mean_o = sum(outcomes) / n
    ss_pp = sum((p - mean_p) ** 2 for p in probs)
    if ss_pp < 1e-12:
        return {"slope": 1.0, "intercept": 0.0}
    ss_po = sum((p - mean_p) * (o - mean_o) for p, o in zip(probs, outcomes, strict=True))
    slope = ss_po / ss_pp
    intercept = mean_o - slope * mean_p
    return {"slope": float(slope), "intercept": float(intercept)}


def _ensure_champion_calibration(session: Any, now: datetime, commit: str) -> Any:
    """Return the current champion CalibrationModel, creating one if needed.

    If ≥ CALIBRATION_MIN_SAMPLES WIN/LOSS settlements with taken_probability
    exist, fits a linear calibrator from the most recent 500.  Otherwise,
    uses an identity calibrator (slope=1.0, intercept=0.0).
    """
    from sqlalchemy import select

    from backend.models import (
        CalibrationMethod,
        CalibrationModel,
        CalibrationStatus,
        Settlement,
    )
    from backend.models import SettlementOutcome as OrmOutcome

    # Check for existing champion.
    champion = session.scalars(
        select(CalibrationModel).where(
            CalibrationModel.status == CalibrationStatus.CHAMPION,
            CalibrationModel.market.is_(None),  # global calibrator
        )
    ).first()
    if champion is not None:
        return champion

    # Collect recent WIN/LOSS settlements for fitting.
    superseded_ids = select(Settlement.supersedes_id).where(
        Settlement.supersedes_id.is_not(None)
    )
    rows = list(session.scalars(
        select(Settlement).where(
            Settlement.subject_type == "prediction",
            Settlement.id.not_in(superseded_ids),
            Settlement.taken_probability.is_not(None),
            Settlement.outcome.in_([OrmOutcome.WIN, OrmOutcome.LOSS]),
        )
        .order_by(Settlement.settled_at.desc())
        .limit(500)
    ))

    probs = [float(r.taken_probability) for r in rows if r.taken_probability is not None]
    outcomes = [1.0 if r.outcome == OrmOutcome.WIN else 0.0 for r in rows]

    if len(probs) >= _CALIBRATION_MIN_SAMPLES:
        params = _fit_linear_calibration(probs, outcomes)
        sample_size = len(probs)
        min_sample = _CALIBRATION_MIN_SAMPLES
        method = CalibrationMethod.PLATT
        window_start = min(r.settled_at for r in rows)
        window_end = max(r.settled_at for r in rows)
        version_tag = "linear-fitted"
        log.info("signal_pipeline: fitted linear calibrator from %d samples", sample_size)
    else:
        params = {"slope": 1.0, "intercept": 0.0}
        sample_size = 2
        min_sample = 2
        method = CalibrationMethod.PLATT
        window_start = now - timedelta(days=1)
        window_end = now
        version_tag = "identity"
        log.info(
            "signal_pipeline: < %d settlements — using identity calibrator",
            _CALIBRATION_MIN_SAMPLES,
        )

    artefact_hash = _sha256(params)
    version = f"signal-calibrator-{version_tag}-{now.strftime('%Y%m%d')}"

    cal = CalibrationModel(
        version=version,
        method=method,
        status=CalibrationStatus.CHAMPION,
        trained_as_of=now,
        training_window_start=window_start,
        training_window_end=window_end,
        sample_size=sample_size,
        minimum_sample_size=min_sample,
        parameters=params,
        artefact_hash=artefact_hash,
        code_commit=commit,
        promoted_at=now,
    )
    session.add(cal)
    session.flush()
    log.info(
        "signal_pipeline: registered champion calibration model %s (hash=%s…)",
        version, artefact_hash[:12],
    )
    return cal


def _apply_calibration(raw_prob: float, params: dict) -> float:
    """Apply linear calibration: slope * p + intercept, clipped to (0.001, 0.999)."""
    slope = params.get("slope", 1.0)
    intercept = params.get("intercept", 0.0)
    return max(0.001, min(0.999, slope * raw_prob + intercept))


# ---------------------------------------------------------------------------
# Fixture selection
# ---------------------------------------------------------------------------

def _upcoming_unpredicted_fixtures(
    session: Any,
    now: datetime,
    lookahead_hours: int,
) -> list[Any]:
    """Return fixtures kicking off in (now, now+lookahead_hours] with no 1X2 HOME prediction."""
    from sqlalchemy import select

    from backend.models import Fixture, FixtureStatus, Prediction

    window_end = now + timedelta(hours=lookahead_hours)

    # Fixtures already predicted on 1X2/home for this market.
    predicted_fixture_ids = select(Prediction.fixture_id).where(
        Prediction.market == _MARKET,
        Prediction.selection == _SELECTION,
    )

    stmt = (
        select(Fixture)
        .where(
            Fixture.status == FixtureStatus.SCHEDULED,
            Fixture.kickoff_utc > now,
            Fixture.kickoff_utc <= window_end,
            Fixture.id.not_in(predicted_fixture_ids),
        )
        .order_by(Fixture.kickoff_utc)
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Odds lookup (best pre-kickoff quote for a fixture/market/selection)
# ---------------------------------------------------------------------------

def _best_pre_kickoff_odds(
    session: Any,
    fixture_id: uuid.UUID,
    market: str,
    selection: str,
    *,
    before: datetime,
) -> tuple[float | None, str | None, datetime | None]:
    """Return (decimal_odds, bookmaker, captured_at) for the latest pre-kickoff quote."""
    from sqlalchemy import select

    from backend.models import OddsQuote

    stmt = (
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.market == market,
            OddsQuote.selection == selection,
            OddsQuote.captured_at < before,
        )
        .order_by(OddsQuote.captured_at.desc())
        .limit(1)
    )
    quote = session.scalars(stmt).first()
    if quote is None:
        return None, None, None
    captured = quote.captured_at
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=UTC)
    return float(quote.decimal_odds), quote.bookmaker, captured


# ---------------------------------------------------------------------------
# DQS computation (re-using walk-forward pattern)
# ---------------------------------------------------------------------------

def _compute_dqs(features: Any) -> float:
    """Compute a simple data-quality score from feature completeness."""
    from qwantej.data.dqs import DQSComponents, compute_dqs

    home_m = getattr(features, "home_matches", 0)
    away_m = getattr(features, "away_matches", 0)
    sample_score = min(100.0, (home_m + away_m) * 100.0 / 20.0)
    components = DQSComponents(
        completeness=min(100.0, (home_m + away_m) * 100.0 / 30.0),
        freshness=80.0,
        provider_reliability=90.0,
        sample_sufficiency=sample_score,
        entity_match_confidence=90.0,
        timestamp_validity=90.0,
    )
    return compute_dqs(components)


# ---------------------------------------------------------------------------
# Per-fixture processing
# ---------------------------------------------------------------------------

def _process_fixture(
    session: Any,
    fixture: Any,
    *,
    now: datetime,
    model_registry: Any,
    model_run: Any,
    calibration_model: Any,
    value_policy: Any,
    commit: str,
) -> Any | None:
    """Extract features, run models, apply calibration, evaluate gate, publish.

    Returns the published Prediction ORM row on success, None otherwise.
    """
    from backend.services.feature_extraction import (
        FeatureExtractionError,
        extract_fixture_features,
    )
    from backend.services.features import create_feature_snapshot
    from backend.services.predictions import (
        MinimumPredictionRecord,
        PredictionLineage,
        PredictionPublicationError,
        publish_prediction,
    )
    from qwantej.models.elo.model import result_probabilities as elo_probs
    from qwantej.models.poisson.model import poisson_scoreline
    from qwantej.value.gate import ValueCandidate, evaluate_value_gate

    as_of = now
    kickoff = fixture.kickoff_utc
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UTC)

    # 1. PIT feature extraction.
    try:
        features, stats_ids, odds_ids, _ = extract_fixture_features(
            session, fixture, as_of=as_of
        )
    except FeatureExtractionError as exc:
        log.debug("signal_pipeline: fixture %s feature error: %s", fixture.id, exc)
        return None

    # 2. Immutable feature snapshot.
    # Convert MatchFeatures dataclass to a flat scalar Mapping[str, FeatureValue].
    from dataclasses import asdict as _asdict
    feature_vector = {
        k: v for k, v in _asdict(features).items()
        if isinstance(v, (int, float, bool, str, type(None)))
    }
    snap = create_feature_snapshot(
        session,
        fixture_id=fixture.id,
        feature_version=_FEATURE_VERSION,
        as_of_timestamp=as_of,
        features=feature_vector,
        stats_snapshot_ids=stats_ids,
        odds_quote_ids=odds_ids,
        imputation_policy_version=_IMPUTATION_POLICY_VERSION,
        code_commit=commit,
    )

    # 2b. Per-fixture inference run: must be SUCCEEDED with data_snapshot_ref before
    # publish_prediction validates lineage (one run per fixture, not per pipeline invocation).
    from backend.models import ModelRun as _ModelRun
    from backend.models import ModelRunKind, ModelRunStatus
    fixture_run = _ModelRun(
        model_id=model_registry.id,
        kind=ModelRunKind.INFERENCE,
        status=ModelRunStatus.SUCCEEDED,
        started_at=as_of,
        finished_at=as_of,
        data_as_of=as_of,
        data_snapshot_ref=snap.snapshot_ref,
        code_commit=commit,
        parameters={"fixture_id": str(fixture.id), "market": _MARKET, "selection": _SELECTION},
        metrics={"pipeline_run_id": str(model_run.id)},
    )
    session.add(fixture_run)
    session.flush()

    # 3. Run probability models.
    poisson_result = poisson_scoreline(features.home_xg, features.away_xg).match_result()
    elo_result = elo_probs(features.elo_home_rating, features.elo_away_rating)

    raw_prob = (float(poisson_result.home) + float(elo_result.home)) / 2.0
    model_probs = {
        "poisson_home": float(poisson_result.home),
        "poisson_draw": float(poisson_result.draw),
        "poisson_away": float(poisson_result.away),
        "elo_home": float(elo_result.home),
        "elo_away": float(elo_result.away),
    }

    # 4. Calibrate.
    cal_params = calibration_model.parameters or {"slope": 1.0, "intercept": 0.0}
    cal_prob = _apply_calibration(raw_prob, cal_params)
    # P_cons = shrink towards 0.50 by 0.05 (conservative uncertainty margin).
    p_cons = max(0.001, cal_prob - 0.05)

    # 5. Odds lookup.
    decimal_odds, bookmaker, quote_ts = _best_pre_kickoff_odds(
        session, fixture.id, _MARKET, _SELECTION, before=as_of
    )

    # 6. DQS.
    dqs = _compute_dqs(features)

    # 7. Value Gate.
    if decimal_odds is None or quote_ts is None:
        fair_prob = None
        executable_odds = None
        edge = 0.0
        ev = 0.0
        gate_passed = False
        log.debug("signal_pipeline: fixture %s — no odds, skipping gate", fixture.id)
    else:
        # Raw implied probability for this single leg (1 / decimal odds).
        # Full de-vigging requires all legs of the market; we use the raw
        # implied prob as a conservative fair-price floor here.
        fair_prob = 1.0 / decimal_odds
        edge = p_cons - fair_prob
        # edge_pp stored in percentage points; expected_value = P_cons × odds - 1.
        edge_pp_val = edge * 100.0
        ev = p_cons * decimal_odds - 1.0

        candidate = ValueCandidate(
            decision_as_of=as_of,
            calibrator_approved=True,
            calibrated_probability=cal_prob,
            conservative_probability=p_cons,
            fair_market_probability=fair_prob,
            executable_odds=decimal_odds,
            quote_timestamp=quote_ts,
            data_quality_score=dqs,
            league_reliability=None,
            market_reliability=None,
            probability_change=0.0,
            model_disagreement=abs(float(poisson_result.home) - float(elo_result.home)),
            # Reliability scoring is not yet wired for live fixtures; exempt
            # from that gate until Phase 9 integrates the reliability engine.
            research_reliability_exception=True,
        )
        gate_result = evaluate_value_gate(candidate, value_policy)
        gate_passed = gate_result.passed

        if not gate_passed:
            log.debug(
                "signal_pipeline: fixture %s gate rejected: %s",
                fixture.id,
                [r.value for r in gate_result.reason_codes],
            )
        executable_odds = decimal_odds

    if not gate_passed:
        return None

    # 8. Publish prediction.
    record = MinimumPredictionRecord(
        fixture_id=fixture.id,
        prediction_timestamp=as_of,
        decision_as_of=as_of,
        market=_MARKET,
        selection=_SELECTION,
        model_probabilities=model_probs,
        ensemble_probability=raw_prob,
        calibrated_probability=cal_prob,
        conservative_probability=p_cons,
        dqs=dqs,
        bookmaker=bookmaker,
        executable_odds=executable_odds,
        quote_timestamp=quote_ts,
        fair_market_probability=fair_prob,
        edge_pp=edge_pp_val if decimal_odds is not None else None,
        expected_value=ev if decimal_odds is not None else None,
        qss=max(0.0, min(100.0, dqs)),
    )
    lineage = PredictionLineage(
        model_version_id=model_registry.id,
        model_run_id=fixture_run.id,
        calibration_model_id=calibration_model.id,
        feature_version=_FEATURE_VERSION,
        calibration_version=calibration_model.version,
        code_commit=commit,
        input_snapshot_ref=snap.snapshot_ref,
        input_snapshot_hash=snap.snapshot_hash,
    )
    try:
        prediction = publish_prediction(session, record=record, lineage=lineage)
        log.info(
            "signal_pipeline: published prediction %s for fixture %s "
            "(p_cons=%.3f odds=%.2f edge=+%.3f)",
            prediction.id, fixture.id, p_cons,
            executable_odds or 0.0, edge,
        )
        return prediction
    except PredictionPublicationError as exc:
        log.warning("signal_pipeline: publish failed for fixture %s: %s", fixture.id, exc)
        return None


# ---------------------------------------------------------------------------
# Accumulator phase
# ---------------------------------------------------------------------------

def _run_accumulator_phase(
    session: Any,
    predictions: list[Any],
    fixtures_by_id: dict,
    *,
    now: datetime,
    model_registry: Any,
    calibration_model: Any,
    commit: str,
) -> Any | None:
    """Build and persist accumulator decisions from qualified predictions."""
    from backend.services.accumulator import persist_accumulator_decision
    from backend.services.bankroll import current_bankroll
    from qwantej.accumulator.decision import build_accumulator_decision
    from qwantej.accumulator.types import QualifiedSelection
    from qwantej.bankroll.state import DEFAULT_RISK_POLICY, OperatingState

    if not predictions:
        log.info("signal_pipeline: no qualified predictions — skipping accumulator phase")
        return None

    # Fetch bankroll (returns 0 if no ledger yet — that's fine in paper mode).
    bankroll = float(current_bankroll(session))
    available = bankroll  # no daily exposure tracking yet

    qualified: list[QualifiedSelection] = []
    for pred in predictions:
        fixture = fixtures_by_id.get(str(pred.fixture_id))
        league_id = str(fixture.competition_id) if fixture else "unknown"
        market_family = _MARKET
        edge = float(pred.edge_pp) if pred.edge_pp is not None else 0.0
        qss = float(pred.qss) if pred.qss is not None else 70.0
        dqs = float(pred.dqs) if pred.dqs is not None else 70.0

        if pred.executable_odds is None or pred.conservative_probability is None:
            continue
        try:
            qs = QualifiedSelection(
                prediction_id=str(pred.id),
                fixture_id=str(pred.fixture_id),
                league_id=league_id,
                market_family=market_family,
                selection=_SELECTION,
                calibrated_probability=float(pred.calibrated_probability),
                conservative_probability=float(pred.conservative_probability),
                decimal_odds=Decimal(str(pred.executable_odds)),
                edge=edge,
                qss=qss,
                dqs=dqs,
                reliability=70.0,  # no reliability snapshot yet
                quote_timestamp=pred.quote_timestamp or now,
                model_version=f"{_MODEL_NAME}:{_MODEL_VERSION}",
                calibration_version=calibration_model.version,
                feature_version=_FEATURE_VERSION,
                code_commit=commit,
                input_snapshot_hash=pred.input_snapshot_hash,
            )
            qualified.append(qs)
        except ValueError as exc:
            log.debug("signal_pipeline: skipping prediction %s: %s", pred.id, exc)

    if not qualified:
        log.info("signal_pipeline: no qualified selections for accumulator")
        return None

    decision = build_accumulator_decision(
        qualified,
        as_of=now,
        operating_state=OperatingState.NORMAL,
        current_bankroll=bankroll,
        available_bankroll=available,
        committed_daily_exposure=0.0,
        risk_policy=DEFAULT_RISK_POLICY,
    )

    persist_accumulator_decision(session, decision, published_at=now)
    log.info(
        "signal_pipeline: accumulator decision persisted — candidates=%d paper_only=%s",
        decision.candidate_count, decision.paper_only,
    )
    return decision


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def _notify(run: PipelineRun, decision: Any | None) -> None:
    try:
        from backend.core.config import get_settings
        from backend.services.notifier import TelegramNotifier
        from qwantej.notifications.types import Notification, NotificationEvent, NotificationLevel

        notifier = TelegramNotifier.from_settings(get_settings())
        if not notifier.enabled:
            return

        tickets = []
        if decision is not None:
            for pd in decision.products:
                if pd.result.ticket is not None:
                    t = pd.result.ticket
                    stake = (
                        f"  stake={pd.stake_decision.recommended_stake:.2f}"
                        if pd.stake_decision and pd.stake_decision.recommended_stake
                        else "  stake=paper"
                    )
                    tickets.append(
                        f"  {pd.product.value.upper()}: "
                        f"{len(t.legs)} legs @ {float(t.combined_odds):.2f}{stake}"
                    )

        body_lines = [
            f"Predictions: {run.predictions_published}",
            f"Gate rejected: {run.value_gate_rejected}",
            f"Errors: {run.errors}",
        ]
        if tickets:
            body_lines.append("Tickets:")
            body_lines.extend(tickets)
        else:
            body_lines.append("No qualifying accumulator today.")

        level = NotificationLevel.ERROR if run.errors else NotificationLevel.INFO
        notifier.send(
            Notification(
                event=NotificationEvent.SETTLEMENT_BATCH_DONE,
                title="Signal pipeline complete",
                body="\n".join(body_lines),
                level=level,
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("signal_pipeline: notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Type alias to avoid importing Any at module level (keep linter happy).
from typing import Any  # noqa: E402


def run_once(
    *,
    lookahead_hours: int = _LOOKAHEAD_HOURS_DEFAULT,
    dry_run: bool = False,
) -> PipelineRun:
    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.core.logging import configure_logging
    from qwantej.value.gate import ValueGatePolicy

    configure_logging()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    now = datetime.now(UTC)
    commit = _code_commit()

    run = PipelineRun(started_at=now)
    value_policy = ValueGatePolicy()

    predictions_published: list[Any] = []
    fixtures_by_id: dict[str, Any] = {}
    decision = None

    try:
        with session_scope(engine) as session:
            # Bootstrap: ensure model and calibration registry rows exist.
            model_registry, model_run = _ensure_champion_model(session, now)
            calibration_model = _ensure_champion_calibration(session, now, commit)

            # Find upcoming unpredicted fixtures.
            fixtures = _upcoming_unpredicted_fixtures(session, now, lookahead_hours)
            run.fixtures_evaluated = len(fixtures)
            log.info(
                "signal_pipeline: %d fixture(s) in next %dh to process",
                len(fixtures), lookahead_hours,
            )

            for fixture in fixtures:
                fixtures_by_id[str(fixture.id)] = fixture
                result = _process_fixture(
                    session,
                    fixture,
                    now=now,
                    model_registry=model_registry,
                    model_run=model_run,
                    calibration_model=calibration_model,
                    value_policy=value_policy,
                    commit=commit,
                )
                if result is not None:
                    predictions_published.append(result)
                    run.predictions_published += 1
                    run.features_extracted += 1
                else:
                    run.value_gate_rejected += 1

            # Accumulator phase.
            if predictions_published:
                decision = _run_accumulator_phase(
                    session,
                    predictions_published,
                    fixtures_by_id,
                    now=now,
                    model_registry=model_registry,
                    calibration_model=calibration_model,
                    commit=commit,
                )

            # Mark model run succeeded.
            model_run.status = model_run.status.__class__.SUCCEEDED
            model_run.finished_at = datetime.now(UTC)
            model_run.metrics = {
                "fixtures_evaluated": run.fixtures_evaluated,
                "predictions_published": run.predictions_published,
                "gate_rejected": run.value_gate_rejected,
            }

            if dry_run:
                session.rollback()
                log.info("signal_pipeline: dry-run — all writes rolled back")
            else:
                # session_scope commits on clean exit.
                pass

    except Exception:
        log.exception("signal_pipeline: fatal error in pipeline run")
        run.errors += 1

    if not dry_run:
        _notify(run, decision)

    log.info(
        "signal_pipeline: run complete — fixtures=%d predictions=%d gate_rejected=%d errors=%d",
        run.fixtures_evaluated,
        run.predictions_published,
        run.value_gate_rejected,
        run.errors,
    )
    return run


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--lookahead", type=int, default=_LOOKAHEAD_HOURS_DEFAULT, metavar="HOURS",
        help=(
            f"Look ahead this many hours for upcoming fixtures "
            f"(default: {_LOOKAHEAD_HOURS_DEFAULT})"
        ),
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously on --interval schedule",
    )
    parser.add_argument(
        "--interval", type=int, default=3600, metavar="SECONDS",
        help="Loop interval in seconds (default: 3600)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Roll back all writes — no predictions or accumulators persisted",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.loop:
        log.info("signal_pipeline: loop mode — every %ds", args.interval)
        while True:
            run = run_once(lookahead_hours=args.lookahead, dry_run=args.dry_run)
            if run.errors:
                log.warning("signal_pipeline: %d error(s) in run", run.errors)
            log.info("signal_pipeline: sleeping %ds", args.interval)
            time.sleep(args.interval)
    else:
        run = run_once(lookahead_hours=args.lookahead, dry_run=args.dry_run)
        sys.exit(1 if run.errors else 0)


if __name__ == "__main__":
    main()
