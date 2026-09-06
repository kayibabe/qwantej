"""Shared probability result types for the prediction engine (framework §16, §19).

Every baseline model ultimately emits market probabilities in these small,
validated, immutable containers so the ensemble, value and calibration layers
downstream consume one uniform shape regardless of which model produced them.
These are *raw* model probabilities (P_raw, framework §19) — calibration and
the conservative haircut are applied later, in Phase 4.
"""

from dataclasses import dataclass

# Probabilities are floating-point; a derived distribution should sum to 1 up
# to rounding across a truncated scoreline matrix and repeated additions.
SUM_TOLERANCE = 1e-6


def _check_unit(name: str, value: float) -> None:
    if not -1e-9 <= value <= 1 + 1e-9:
        raise ValueError(f"{name} must be a probability in [0, 1], got {value}")


@dataclass(frozen=True)
class MatchResultProbs:
    """1X2 (home win / draw / away win)."""

    home: float
    draw: float
    away: float

    def __post_init__(self) -> None:
        for name in ("home", "draw", "away"):
            _check_unit(name, getattr(self, name))
        total = self.home + self.draw + self.away
        if abs(total - 1.0) > SUM_TOLERANCE:
            raise ValueError(f"MatchResultProbs must sum to 1, got {total}")

    def double_chance(self) -> "DoubleChanceProbs":
        return DoubleChanceProbs(
            home_or_draw=self.home + self.draw,
            home_or_away=self.home + self.away,
            draw_or_away=self.draw + self.away,
        )

    def as_dict(self) -> dict[str, float]:
        return {"home": self.home, "draw": self.draw, "away": self.away}


@dataclass(frozen=True)
class DoubleChanceProbs:
    """1X / 12 / X2. Each is the union of two mutually exclusive outcomes, so
    the three do NOT sum to 1 (each pair overlaps in the 1X2 space)."""

    home_or_draw: float  # 1X
    home_or_away: float  # 12
    draw_or_away: float  # X2

    def __post_init__(self) -> None:
        for name in ("home_or_draw", "home_or_away", "draw_or_away"):
            _check_unit(name, getattr(self, name))

    def as_dict(self) -> dict[str, float]:
        return {"1X": self.home_or_draw, "12": self.home_or_away, "X2": self.draw_or_away}


@dataclass(frozen=True)
class BinaryProbs:
    """A two-outcome market (over/under, BTTS yes/no, team over/under)."""

    yes: float
    no: float

    def __post_init__(self) -> None:
        _check_unit("yes", self.yes)
        _check_unit("no", self.no)
        total = self.yes + self.no
        if abs(total - 1.0) > SUM_TOLERANCE:
            raise ValueError(f"BinaryProbs must sum to 1, got {total}")

    def as_dict(self) -> dict[str, float]:
        return {"yes": self.yes, "no": self.no}
