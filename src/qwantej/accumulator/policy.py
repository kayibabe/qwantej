"""Per-product accumulator policies (framework §28–30, ACCUMULATOR_POLICY.md)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from qwantej.bankroll.state import ProductTier


@dataclass(frozen=True)
class AccumulatorPolicy:
    """Thresholds and constraints for one product tier.

    All numeric thresholds are research defaults from ACCUMULATOR_POLICY.md
    and must be validated against backtested data before live deployment.
    """

    version: str
    product: ProductTier
    min_combined_odds: Decimal
    max_combined_odds: Decimal
    min_legs: int
    max_legs: int
    preferred_qss: float
    hard_qss_floor: float
    min_dqs: float
    max_legs_per_league: int
    max_legs_per_market_family: int
    price_freshness_max_age: timedelta
    beam_width: int = 64

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("policy version must not be blank")
        if self.min_combined_odds >= self.max_combined_odds:
            raise ValueError("min_combined_odds must be < max_combined_odds")
        if self.min_legs < 2:
            raise ValueError("min_legs must be at least 2")
        if self.min_legs > self.max_legs:
            raise ValueError("min_legs must be <= max_legs")
        for name, value in (
            ("preferred_qss", self.preferred_qss),
            ("hard_qss_floor", self.hard_qss_floor),
            ("min_dqs", self.min_dqs),
        ):
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be in [0, 100]")
        if self.hard_qss_floor > self.preferred_qss:
            raise ValueError("hard_qss_floor must be <= preferred_qss")
        if self.beam_width < 1:
            raise ValueError("beam_width must be at least 1")

    @classmethod
    def default_for(cls, product: ProductTier) -> AccumulatorPolicy:
        """Research-default policy for each product tier.

        These are initial values from ACCUMULATOR_POLICY.md and must be
        replaced by backtested thresholds before production use.
        """
        if product is ProductTier.CORE:
            return cls(
                version="accumulator-policy-core-v1",
                product=ProductTier.CORE,
                min_combined_odds=Decimal("3.00"),
                max_combined_odds=Decimal("5.00"),
                min_legs=3,
                max_legs=4,
                preferred_qss=87.0,
                hard_qss_floor=82.0,
                min_dqs=70.0,
                max_legs_per_league=2,
                max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2),
            )
        if product is ProductTier.GROWTH:
            return cls(
                version="accumulator-policy-growth-v1",
                product=ProductTier.GROWTH,
                min_combined_odds=Decimal("5.01"),
                max_combined_odds=Decimal("10.00"),
                min_legs=4,
                max_legs=6,
                preferred_qss=85.0,
                hard_qss_floor=82.0,
                min_dqs=70.0,
                max_legs_per_league=2,
                max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2),
            )
        if product is ProductTier.ALPHA:
            return cls(
                version="accumulator-policy-alpha-v1",
                product=ProductTier.ALPHA,
                min_combined_odds=Decimal("10.01"),
                max_combined_odds=Decimal("20.00"),
                min_legs=5,
                max_legs=7,
                preferred_qss=82.0,
                hard_qss_floor=82.0,
                min_dqs=70.0,
                max_legs_per_league=2,
                max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2),
            )
        raise ValueError(f"no default policy for product {product!r}")
