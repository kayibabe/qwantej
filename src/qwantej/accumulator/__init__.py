"""Accumulator Optimiser (framework §28–33).

Constructs CORE/GROWTH/ALPHA tickets from a pool of value-gate-qualified
legs under concentration, dependence, and odds-band constraints.

Public API::

    from qwantej.accumulator import (
        AccumulatorLeg,
        AccumulatorPolicy,
        AccumulatorResult,
        AccumulatorRejectionReason,
        AccumulatorTicket,
        build_ticket,
    )
"""

from qwantej.accumulator.optimiser import AccumulatorResult, build_ticket
from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import (
    AccumulatorLeg,
    AccumulatorRejectionReason,
    AccumulatorTicket,
)

__all__ = [
    "AccumulatorLeg",
    "AccumulatorPolicy",
    "AccumulatorResult",
    "AccumulatorRejectionReason",
    "AccumulatorTicket",
    "build_ticket",
]
