"""Deterministic replay verification: re-run, prove determinism, byte-compare."""

from dataclasses import dataclass
from decimal import Decimal

from qwantej.audit import canonical_hash, verify_replay
from qwantej.audit.reproducibility import check_reproducibility

INPUTS = {"home_attack": 1.4, "away_defence": 0.9, "seed": 20260906}


def _model(inputs: dict) -> dict:
    # Deterministic function of the recorded inputs.
    lam = inputs["home_attack"] * inputs["away_defence"]
    return {"home_win": round(lam / (lam + 1.0), 6)}


def test_faithful_replay_is_verified() -> None:
    archived = _model(INPUTS)
    report = verify_replay(
        recorded_inputs=INPUTS, archived_outputs=archived,
        input_snapshot_hash=canonical_hash(INPUTS), recompute=_model,
    )
    assert report.verified
    assert report.input_integrity and report.deterministic and report.outputs_match
    assert report.differences == ()


def test_nondeterministic_model_fails() -> None:
    calls = {"n": 0}

    def flaky(_inputs: dict) -> dict:
        calls["n"] += 1
        return {"home_win": calls["n"]}

    report = verify_replay(
        recorded_inputs=INPUTS, archived_outputs={"home_win": 1},
        input_snapshot_hash=canonical_hash(INPUTS), recompute=flaky,
    )
    assert not report.verified
    assert not report.deterministic
    assert "non-deterministic" in report.differences[0]


def test_output_mismatch_is_reported() -> None:
    report = verify_replay(
        recorded_inputs=INPUTS, archived_outputs={"home_win": 0.999},
        input_snapshot_hash=canonical_hash(INPUTS), recompute=_model,
    )
    assert not report.verified
    assert report.deterministic and not report.outputs_match
    assert any("does not match the archived output" in d for d in report.differences)


def test_tampered_inputs_fail_hash_check() -> None:
    report = verify_replay(
        recorded_inputs=INPUTS, archived_outputs=_model(INPUTS),
        input_snapshot_hash="sha256:not-the-real-hash", recompute=_model,
    )
    assert not report.verified
    assert not report.input_integrity


def test_value_equivalence_ignores_float_vs_decimal() -> None:
    report = verify_replay(
        recorded_inputs={"a": 1}, archived_outputs={"p": Decimal("0.50")},
        input_snapshot_hash=canonical_hash({"a": 1}),
        recompute=lambda _inp: {"p": 0.5},
    )
    assert report.verified


@dataclass
class _Archived:
    model_version_id: object = "m1"
    feature_version: str = "f1"
    calibration_version: str = "c1"
    risk_policy_version: str = "r1"
    optimiser_version: str = "o1"
    code_commit: str = "abc"
    model_run_id: object = "run1"
    input_snapshot_ref: str = "snapshot:v1"
    input_snapshot_hash: str = "sha256:x"


def test_reproducible_only_when_replay_is_verified() -> None:
    prediction = _Archived()
    verified = verify_replay(
        recorded_inputs=INPUTS, archived_outputs=_model(INPUTS),
        input_snapshot_hash=canonical_hash(INPUTS), recompute=_model,
    ).verified
    report = check_reproducibility(prediction, replay_verified=verified)
    assert report.reproducible
    # Without the verified replay, the same record is only replay-ready.
    assert not check_reproducibility(prediction, replay_verified=False).reproducible
