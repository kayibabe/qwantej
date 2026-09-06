"""De-vig and market-baseline tests (framework §20-21, §51)."""

import pytest

from qwantej.markets.devig import devig, implied_probabilities
from qwantej.models.market import market_probabilities, market_result_probabilities


class TestDevig:
    def test_proportional_removes_margin(self) -> None:
        # A fair 2-way book at 2.00/2.00 has no margin.
        result = devig([2.0, 2.0])
        assert result.overround == pytest.approx(1.0)
        assert result.fair == pytest.approx((0.5, 0.5))

    def test_proportional_sums_to_one_with_margin(self) -> None:
        result = devig([1.90, 3.50, 4.20])  # a real 1X2 book with vig
        assert result.overround > 1.0
        assert sum(result.fair) == pytest.approx(1.0)

    def test_additive_matches_proportional_at_zero_margin(self) -> None:
        prop = devig([2.0, 2.0], method="proportional")
        add = devig([2.0, 2.0], method="additive")
        assert add.fair == pytest.approx(prop.fair)

    def test_additive_rejects_when_it_would_go_negative(self) -> None:
        # A pathological high-overround 3-way book: two short prices inflate the
        # margin past the longshot's tiny implied probability, so the
        # equal-margin subtraction underflows and must be refused.
        with pytest.raises(ValueError):
            devig([1.20, 1.20, 15.0], method="additive")

    def test_implied_probabilities(self) -> None:
        assert implied_probabilities([2.0, 4.0]) == pytest.approx((0.5, 0.25))

    @pytest.mark.parametrize("odds", [[2.0], [2.0, 1.0], [0.9, 2.0]])
    def test_invalid_odds_rejected(self, odds: list[float]) -> None:
        with pytest.raises(ValueError):
            devig(odds)

    @pytest.mark.parametrize("odds", [[float("nan"), 2.0], [2.0, float("inf")]])
    def test_non_finite_odds_rejected(self, odds: list[float]) -> None:
        with pytest.raises(ValueError):
            devig(odds)

    def test_unknown_method_rejected(self) -> None:
        with pytest.raises(ValueError):
            devig([2.0, 2.0], method="shin")


class TestMarketBaseline:
    def test_result_probabilities_sum_to_one(self) -> None:
        mr = market_result_probabilities(1.90, 3.50, 4.20)
        assert mr.home + mr.draw + mr.away == pytest.approx(1.0)
        assert mr.home > mr.away  # shortest price is the favourite

    def test_generic_market_preserves_selection_keys(self) -> None:
        fair = market_probabilities({"over": 1.80, "under": 2.10})
        assert set(fair) == {"over", "under"}
        assert sum(fair.values()) == pytest.approx(1.0)
        assert fair["over"] > fair["under"]
