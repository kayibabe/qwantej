"""Accumulator decision orchestration (framework §28–36, Phase 8).

`build_accumulator_decision` is the single entry point for the accumulator
engine. It accepts a frozen candidate pool, converts each QualifiedSelection
to an AccumulatorLeg, runs build_ticket for each product tier, and calls
recommend_stake against the bankroll state for every ticket that was found.

Design constraints:
- Pure function — no I/O.  The caller (service layer) handles persistence.
- Paper-only flag is always True until production wiring is complete (see
  DEVELOPMENT.md §4 — paper validation required before publication/locking).
- Manifest hash: SHA-256 of the sorted candidate fingerprints.  The sort key
  is prediction_id so the hash is stable regardless of pool ordering.
- Joint probability uses Π P_cons (independence baseline); the stress haircut
  and dependence penalty remain explicitly labelled as proxies (§31).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from qwantej.accumulator.optimiser import AccumulatorResult, build_ticket
from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import QualifiedSelection
from qwantej.bankroll.staking import StakeCandidate, StakeDecision, recommend_stake
from qwantej.bankroll.state import (
    DEFAULT_RISK_POLICY,
    OperatingState,
    ProductTier,
    RiskPolicy,
)

_PRODUCTS = (ProductTier.CORE, ProductTier.GROWTH, ProductTier.ALPHA)

OPTIMISER_VERSION = "accumulator-orchestration-v1"


@dataclass(frozen=True)
class AccumulatorProductDecision:
    """Optimiser result and stake decision for one product tier."""

    product: ProductTier
    result: AccumulatorResult
    stake_decision: StakeDecision | None


@dataclass(frozen=True)
class AccumulatorDecision:
    """Top-level output of one accumulator engine run.

    `paper_only` is always True in Phase 8 — no tickets are locked or
    published until the walk-forward backtest completes and an explicit
    release decision is made.
    """

    as_of: datetime
    operating_state: OperatingState
    candidate_count: int
    input_manifest_hash: str
    products: tuple[AccumulatorProductDecision, ...]
    paper_only: bool = True


def build_accumulator_decision(
    candidates: list[QualifiedSelection],
    *,
    as_of: datetime,
    operating_state: OperatingState,
    current_bankroll: float,
    available_bankroll: float,
    committed_daily_exposure: float,
    policies: dict[ProductTier, AccumulatorPolicy] | None = None,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
) -> AccumulatorDecision:
    """Run the accumulator engine over *candidates* and return a full decision.

    Parameters
    ----------
    candidates:
        Pool of value-gate-qualified selections for this run.  Must be a
        snapshot — the caller must not mutate the list after passing it.
    as_of:
        The decision timestamp.  Passed verbatim to build_ticket and used in
        the manifest; must be timezone-aware.
    operating_state:
        Current bankroll operating state (NORMAL / CAUTION / DEFENSIVE /
        REVIEW).  A REVIEW state causes every stake to be rejected.
    current_bankroll, available_bankroll, committed_daily_exposure:
        Bankroll figures forwarded to recommend_stake.
    policies:
        Per-product AccumulatorPolicy overrides.  Defaults to
        AccumulatorPolicy.default_for(product) for any tier not specified.
    risk_policy:
        Risk/staking policy.  Defaults to DEFAULT_RISK_POLICY.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    manifest_hash = _manifest_hash(candidates, as_of)
    legs = [c.to_leg() for c in candidates]

    product_decisions: list[AccumulatorProductDecision] = []
    for product in _PRODUCTS:
        policy = (policies or {}).get(product) or AccumulatorPolicy.default_for(product)
        result = build_ticket(legs, product, policy, as_of=as_of)

        stake_decision: StakeDecision | None = None
        if result.ticket is not None:
            candidate = StakeCandidate(
                ticket_probability=result.ticket.stressed_joint_probability,
                decimal_odds=float(result.ticket.combined_odds),
                product=product,
                current_bankroll=current_bankroll,
                available_bankroll=available_bankroll,
                committed_daily_exposure=committed_daily_exposure,
                operating_state=operating_state,
            )
            stake_decision = recommend_stake(candidate, risk_policy)

        product_decisions.append(
            AccumulatorProductDecision(
                product=product,
                result=result,
                stake_decision=stake_decision,
            )
        )

    return AccumulatorDecision(
        as_of=as_of,
        operating_state=operating_state,
        candidate_count=len(candidates),
        input_manifest_hash=manifest_hash,
        products=tuple(product_decisions),
        paper_only=True,
    )


def _manifest_hash(candidates: list[QualifiedSelection], as_of: datetime) -> str:
    """SHA-256 over the sorted candidate fingerprints + the as_of timestamp.

    Sorted by prediction_id so the hash is independent of pool ordering.
    Each candidate contributes its decision-critical fields; lineage fields
    (model_version, code_commit, etc.) are included so a re-run with a
    different model version produces a different hash even if probabilities
    are numerically identical.
    """
    entries = sorted(
        (
            {
                "prediction_id": c.prediction_id,
                "fixture_id": c.fixture_id,
                "league_id": c.league_id,
                "market_family": c.market_family,
                "selection": c.selection,
                "calibrated_probability": c.calibrated_probability,
                "conservative_probability": c.conservative_probability,
                "decimal_odds": str(c.decimal_odds),
                "edge": c.edge,
                "qss": c.qss,
                "dqs": c.dqs,
                "reliability": c.reliability,
                "quote_timestamp": c.quote_timestamp.isoformat(),
                "model_version": c.model_version,
                "calibration_version": c.calibration_version,
                "feature_version": c.feature_version,
                "code_commit": c.code_commit,
                "input_snapshot_hash": c.input_snapshot_hash,
            }
            for c in candidates
        ),
        key=lambda d: cast(str, d["prediction_id"]),
    )
    payload = json.dumps({"as_of": as_of.isoformat(), "candidates": entries}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
