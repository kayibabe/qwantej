"""Champion-challenger framework for controlled model promotion (framework §43).

Rules (§43):
- Champion: current approved production model/policy.
- Challenger: runs in *shadow mode* — its probabilities are recorded but it
  cannot control live tickets.
- Promotion requires pre-specified criteria, sufficient evidence, and no
  material risk degradation.
- Rollback: prior champion artefacts remain deployable.

All logic here is pure: decisions are data structures that the application
layer can persist and act on.  No database access or side effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ChallengerStatus(StrEnum):
    SHADOW = "shadow"      # accumulating evidence; not eligible for promotion yet
    ELIGIBLE = "eligible"  # criteria met; human review required before promotion
    PROMOTED = "promoted"  # promoted to champion by a governance decision
    REJECTED = "rejected"  # evaluated and rejected (champion retained)


@dataclass(frozen=True)
class PromotionCriteria:
    """Pre-specified thresholds for challenger promotion (§43).

    All comparisons are challenger_metric BETTER THAN champion_metric by at
    least the `min_improvement_*` margin.  "Better" means lower for Brier/log-
    loss, higher for ROI and CLV.

    Args:
        min_sample_size: minimum number of settled predictions for the
            challenger to be eligible for promotion.
        min_brier_improvement: challenger Brier score must be at least this
            much lower than the champion's.  0.0 means any improvement counts.
        min_roi_improvement: challenger ROI must be at least this much higher
            than the champion's.  May be set to 0.0 if ROI is not the primary
            criterion.
        max_drawdown_increase: challenger maximum drawdown may not exceed the
            champion's by more than this fraction (e.g. 0.05 = 5 pp tolerance).
        require_positive_clv: if True, promotion is blocked if challenger mean
            CLV ≤ 0 (would indicate the challenger is not capturing value).
    """

    min_sample_size: int = 200
    min_brier_improvement: float = 0.002
    min_roi_improvement: float = 0.0
    max_drawdown_increase: float = 0.05
    require_positive_clv: bool = True

    def __post_init__(self) -> None:
        if self.min_sample_size < 1:
            raise ValueError("min_sample_size must be at least 1")
        if not math.isfinite(self.min_brier_improvement) or self.min_brier_improvement < 0:
            raise ValueError("min_brier_improvement must be a non-negative finite float")
        if not math.isfinite(self.min_roi_improvement):
            raise ValueError("min_roi_improvement must be finite")
        if not math.isfinite(self.max_drawdown_increase) or self.max_drawdown_increase < 0:
            raise ValueError("max_drawdown_increase must be a non-negative finite float")


@dataclass(frozen=True)
class ModelMetrics:
    """Comparable performance metrics for a champion or challenger model.

    Args:
        model_version: identifier of the model/policy version.
        n_samples: number of settled predictions evaluated.
        brier_score: mean Brier score (lower = better).
        log_loss: mean log-loss (lower = better).
        roi: realised ROI as a fraction (e.g. 0.04 = 4%).
        mean_clv: mean probability-space CLV (higher = better edge capture).
        max_drawdown: maximum peak-to-trough drawdown as a fraction.
    """

    model_version: str
    n_samples: int
    brier_score: float
    log_loss: float
    roi: float
    mean_clv: float
    max_drawdown: float

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise ValueError("model_version must be a non-blank string")
        if self.n_samples < 0:
            raise ValueError("n_samples must be non-negative")
        for name, value in (
            ("brier_score", self.brier_score),
            ("log_loss", self.log_loss),
            ("roi", self.roi),
            ("mean_clv", self.mean_clv),
            ("max_drawdown", self.max_drawdown),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite float")
        if not 0 <= self.brier_score <= 1:
            raise ValueError("brier_score must be in [0, 1]")
        if self.log_loss < 0:
            raise ValueError("log_loss must be non-negative")
        if not 0 <= self.max_drawdown <= 1:
            raise ValueError("max_drawdown must be in [0, 1]")


@dataclass(frozen=True)
class ChallengerEvaluation:
    """Outcome of comparing a challenger against the current champion.

    `status` is the recommended action:
    - SHADOW  → insufficient evidence; keep accumulating.
    - ELIGIBLE → criteria met; promote after human governance sign-off.
    - REJECTED → challenger evaluated but did not improve sufficiently; retain champion.

    `blocking_reasons` lists the criteria that were NOT met (empty if eligible).
    `evidence_summary` is a human-readable summary of the comparison.
    """

    champion: ModelMetrics
    challenger: ModelMetrics
    criteria: PromotionCriteria
    status: ChallengerStatus
    blocking_reasons: list[str]
    evidence_summary: str


def evaluate_challenger(
    champion: ModelMetrics,
    challenger: ModelMetrics,
    criteria: PromotionCriteria,
) -> ChallengerEvaluation:
    """Evaluate whether a challenger model is ready for promotion.

    Returns a `ChallengerEvaluation` with status SHADOW, ELIGIBLE, or REJECTED.
    PROMOTED and REJECTED (after human sign-off) are persisted by the
    application layer — this function only produces SHADOW or ELIGIBLE/REJECTED.

    The decision logic is:
    1. If challenger has < `min_sample_size` predictions → SHADOW.
    2. Evaluate all criteria; any failure → REJECTED with reasons listed.
    3. All criteria met → ELIGIBLE (human sign-off required for PROMOTED).
    """
    if challenger.n_samples < criteria.min_sample_size:
        summary = (
            f"Challenger '{challenger.model_version}' has {challenger.n_samples} samples "
            f"(need {criteria.min_sample_size}); remaining in shadow mode."
        )
        return ChallengerEvaluation(
            champion=champion,
            challenger=challenger,
            criteria=criteria,
            status=ChallengerStatus.SHADOW,
            blocking_reasons=[
                f"Insufficient samples: {challenger.n_samples} < {criteria.min_sample_size}"
            ],
            evidence_summary=summary,
        )

    blocking: list[str] = []

    brier_improvement = champion.brier_score - challenger.brier_score
    if brier_improvement < criteria.min_brier_improvement:
        blocking.append(
            f"Brier improvement {brier_improvement:.4f} < required "
            f"{criteria.min_brier_improvement:.4f}"
        )

    roi_improvement = challenger.roi - champion.roi
    if roi_improvement < criteria.min_roi_improvement:
        blocking.append(
            f"ROI improvement {roi_improvement:.4f} < required {criteria.min_roi_improvement:.4f}"
        )

    drawdown_increase = challenger.max_drawdown - champion.max_drawdown
    if drawdown_increase > criteria.max_drawdown_increase:
        blocking.append(
            f"Drawdown increase {drawdown_increase:.4f} > tolerance "
            f"{criteria.max_drawdown_increase:.4f}"
        )

    if criteria.require_positive_clv and challenger.mean_clv <= 0:
        blocking.append(
            f"Challenger mean CLV {challenger.mean_clv:.4f} is not positive"
        )

    status = ChallengerStatus.REJECTED if blocking else ChallengerStatus.ELIGIBLE

    lines = [
        f"Champion '{champion.model_version}' vs Challenger '{challenger.model_version}' "
        f"({challenger.n_samples} samples):",
        f"  Brier: {champion.brier_score:.4f} → {challenger.brier_score:.4f} "
        f"(Δ={brier_improvement:+.4f}, need ≥{criteria.min_brier_improvement:.4f})",
        f"  ROI:   {champion.roi:.4f} → {challenger.roi:.4f} "
        f"(Δ={roi_improvement:+.4f})",
        f"  CLV:   {champion.mean_clv:.4f} → {challenger.mean_clv:.4f}",
        f"  MaxDD: {champion.max_drawdown:.4f} → {challenger.max_drawdown:.4f} "
        f"(increase={drawdown_increase:+.4f}, tol={criteria.max_drawdown_increase:.4f})",
        f"  Status: {status}",
    ]
    if blocking:
        lines.append("  Blocking: " + "; ".join(blocking))

    return ChallengerEvaluation(
        champion=champion,
        challenger=challenger,
        criteria=criteria,
        status=status,
        blocking_reasons=blocking,
        evidence_summary="\n".join(lines),
    )
