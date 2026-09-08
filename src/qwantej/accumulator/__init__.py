"""Accumulator Optimiser (framework §28–36).

Constructs CORE/GROWTH/ALPHA tickets from a pool of value-gate-qualified
legs under concentration, dependence, and odds-band constraints.

Public API::

    from qwantej.accumulator import (
        AccumulatorLeg,
        AccumulatorPolicy,
        AccumulatorResult,
        AccumulatorRejectionReason,
        AccumulatorTicket,
        QualifiedSelection,
        AccumulatorProductDecision,
        AccumulatorDecision,
        build_ticket,
        build_accumulator_decision,
    )
"""

from qwantej.accumulator.decision import (
    AccumulatorDecision,
    AccumulatorProductDecision,
    build_accumulator_decision,
)
from qwantej.accumulator.optimiser import AccumulatorResult, build_ticket
from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import (
    AccumulatorLeg,
    AccumulatorRejectionReason,
    AccumulatorTicket,
    QualifiedSelection,
)

__all__ = [
    "AccumulatorDecision",
    "AccumulatorLeg",
    "AccumulatorPolicy",
    "AccumulatorProductDecision",
    "AccumulatorResult",
    "AccumulatorRejectionReason",
    "AccumulatorTicket",
    "QualifiedSelection",
    "build_accumulator_decision",
    "build_ticket",
]
