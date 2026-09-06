"""Deterministic replay verification for archived predictions (framework §13).

`check_reproducibility` reports whether the *metadata* needed to replay a
prediction is present; it takes ``replay_verified`` on trust. This module
supplies the actual verification step it was waiting for: given the recorded
inputs, the archived outputs and a recompute function, it

1. confirms the recorded inputs hash to the archived ``input_snapshot_hash``
   (the inputs really are what the record claims),
2. runs the recompute twice and confirms the two results are identical (the
   model is deterministic — an unseeded Monte Carlo model fails here), and
3. confirms the recomputed output equals the archived output.

Only when all three hold is the replay verified. Comparison is by canonical
value (numbers normalised through ``Decimal``), so float-vs-``Decimal`` storage
representation does not cause a spurious mismatch, while a genuine difference in
any value does. Like the rest of `qwantej.audit`, it is ORM-decoupled: it works
on plain mappings and a callable, so the same check runs over live rows,
backtest records or archive exports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


def _canonical(value: Any) -> Any:
    """Normalise a value for representation-independent comparison/hashing."""

    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return f"num:{value.normalize():f}"
    if isinstance(value, float):
        return f"num:{Decimal(str(value)).normalize():f}"
    if isinstance(value, int):
        return f"num:{Decimal(value).normalize():f}"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    """Deterministic canonical serialisation used for hashing and comparison."""

    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode()


def canonical_hash(value: Any) -> str:
    """`sha256:<hex>` over the canonical serialisation of ``value``."""

    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ReplayVerification:
    verified: bool
    input_integrity: bool
    deterministic: bool
    outputs_match: bool
    differences: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.verified


def verify_replay(
    *,
    recorded_inputs: Any,
    archived_outputs: Any,
    input_snapshot_hash: str,
    recompute: Callable[[Any], Any],
) -> ReplayVerification:
    """Re-run a model from its recorded inputs and verify the archived output.

    ``recompute`` must be a pure function of ``recorded_inputs`` (plus any seed
    captured inside them); it is called twice to prove determinism.
    """

    differences: list[str] = []

    input_integrity = canonical_hash(recorded_inputs) == input_snapshot_hash
    if not input_integrity:
        differences.append("recorded inputs do not match input_snapshot_hash")

    first = recompute(recorded_inputs)
    second = recompute(recorded_inputs)
    deterministic = canonical_bytes(first) == canonical_bytes(second)
    if not deterministic:
        differences.append("recompute is non-deterministic across runs")

    outputs_match = deterministic and canonical_bytes(first) == canonical_bytes(
        archived_outputs
    )
    if deterministic and not outputs_match:
        differences.append("recomputed output does not match the archived output")

    verified = input_integrity and deterministic and outputs_match
    return ReplayVerification(
        verified=verified,
        input_integrity=input_integrity,
        deterministic=deterministic,
        outputs_match=outputs_match,
        differences=tuple(differences),
    )
