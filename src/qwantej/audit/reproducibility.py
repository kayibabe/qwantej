"""Reproducibility check for archived predictions (framework §13, §51).

Framework §13 requires that every published prediction "remain reproducible
even after models, features or calibrators change", and §13/§235 add: "store
input snapshot identifiers/hashes and the code commit SHA for full
reproduction". Those are two different guarantees, and this module keeps them
distinct:

- **Version completeness** — the six version-spine fields are present. This is
  *attribution*: it says which model, feature, calibration, risk-policy and
  optimiser versions (and code commit) were in force. It does NOT prove the
  prediction can be re-run.

- **Replay readiness** — version-complete and the execution/input reference
  and content hash are recorded. This is the metadata needed to attempt a
  replay; it is not proof that the artifact remains retrievable or reproduces
  the archived output.

- **Reproducibility** — replay-ready and an external replay has successfully
  regenerated and compared the output. Phase 5 owns that execution step.

Deliberately decoupled from the ORM (like `qwantej.data.dqs`): it accepts any
object exposing the fields, so the same check runs over live ORM rows,
backtest records or replayed archive exports alike. Presence is necessary but
not sufficient for true reproduction — actually re-running the model and
byte-comparing outputs is a verification step the backtester owns (Phase 5);
this gate reports readiness separately from verified reproduction.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Attribution: which versions were in force.
REQUIRED_VERSION_FIELDS: tuple[str, ...] = (
    "model_version_id",
    "feature_version",
    "calibration_version",
    "risk_policy_version",
    "optimiser_version",
    "code_commit",
)

# Replay: which run produced the parameters and what exact inputs were fed.
# `prediction_timestamp` and `decision_as_of` are NOT NULL by construction on
# the predictions table, so they are not re-checked here.
REQUIRED_LINEAGE_FIELDS: tuple[str, ...] = (
    "model_run_id",
    "input_snapshot_ref",
    "input_snapshot_hash",
)


@runtime_checkable
class VersionedPrediction(Protocol):
    """Structural type: anything carrying the version spine and lineage."""

    model_version_id: object | None
    feature_version: str | None
    calibration_version: str | None
    risk_policy_version: str | None
    optimiser_version: str | None
    code_commit: str | None
    model_run_id: object | None
    input_snapshot_ref: str | None
    input_snapshot_hash: str | None


@dataclass(frozen=True)
class ReproducibilityReport:
    """Attribution, replay readiness, and verified reproduction are distinct."""

    version_complete: bool
    lineage_complete: bool
    replay_verified: bool
    reproducible: bool
    missing_version_fields: tuple[str, ...]
    missing_lineage_fields: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.reproducible

    @property
    def replayable(self) -> bool:
        """Compatibility alias with strict, verified semantics."""
        return self.reproducible


def _is_blank(value: object | None) -> bool:
    """A field counts as missing if it is None or blank/whitespace."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _missing(prediction: object, fields: Sequence[str]) -> tuple[str, ...]:
    return tuple(name for name in fields if _is_blank(getattr(prediction, name, None)))


def check_reproducibility(
    prediction: VersionedPrediction,
    version_fields: Sequence[str] = REQUIRED_VERSION_FIELDS,
    lineage_fields: Sequence[str] = REQUIRED_LINEAGE_FIELDS,
    *,
    replay_verified: bool = False,
) -> ReproducibilityReport:
    """Report metadata readiness and whether an external replay was verified."""
    missing_version = _missing(prediction, version_fields)
    missing_lineage = _missing(prediction, lineage_fields)
    version_complete = not missing_version
    lineage_complete = version_complete and not missing_lineage
    return ReproducibilityReport(
        version_complete=version_complete,
        lineage_complete=lineage_complete,
        replay_verified=replay_verified,
        reproducible=lineage_complete and replay_verified,
        missing_version_fields=missing_version,
        missing_lineage_fields=missing_lineage,
    )
