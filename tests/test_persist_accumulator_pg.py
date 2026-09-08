"""PostgreSQL-backed concurrency test for persist_accumulator_decision.

SELECT FOR UPDATE is a no-op in SQLite; these tests require the dev Postgres
container and are skipped when it is unreachable or not migrated to head.

Run the dev database with:
    docker compose up -d db
    alembic upgrade head
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
)
from backend.services.accumulator import (
    AccumulatorPersistError,
    persist_accumulator_decision,
)
from qwantej.accumulator import (
    QualifiedSelection,
    build_accumulator_decision,
)
from qwantej.bankroll.state import OperatingState, ProductTier

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)

_LINEAGE = dict(
    model_version="model-v1",
    calibration_version="cal-v1",
    feature_version="feat-v1",
    code_commit="abc123",
)

DATABASE_URL = get_settings().database_url


# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("SELECT FOR UPDATE concurrency test is PostgreSQL-only")
    eng = create_engine(DATABASE_URL)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("dev Postgres not reachable (docker compose up -d db)")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


# ---------------------------------------------------------------------------
# Helpers (same pool parameters as the SQLite tests)
# ---------------------------------------------------------------------------


def _seed_predictions(
    session: Session, count: int
) -> list[tuple[Fixture, Prediction]]:
    comp = Competition(name="PG_ConcurrencyLeague")
    season = Season(competition=comp, label="2026/27")
    home = Team(name="Home")
    away = Team(name="Away")
    session.add_all([comp, season, home, away])
    session.flush()

    pairs: list[tuple[Fixture, Prediction]] = []
    for i in range(count):
        fixture = Fixture(
            competition=comp,
            season=season,
            home_team=home,
            away_team=away,
            kickoff_utc=NOW + timedelta(days=i + 1),
            status=FixtureStatus.SCHEDULED,
        )
        session.add(fixture)
        session.flush()
        prediction = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW,
            decision_as_of=NOW,
            market="1X2",
            selection="home",
            ensemble_probability=0.52,
            calibrated_probability=0.53,
            conservative_probability=0.50,
        )
        session.add(prediction)
        session.flush()
        pairs.append((fixture, prediction))
    return pairs


def _make_qs(fixture: Fixture, prediction: Prediction, *, index: int) -> QualifiedSelection:
    return QualifiedSelection(
        prediction_id=str(prediction.id),
        fixture_id=str(fixture.id),
        league_id=f"L{index % 3}",
        market_family="TOTALS",
        selection="Over 2.5",
        calibrated_probability=0.62,
        conservative_probability=0.60,
        decimal_odds=Decimal("1.70"),
        edge=0.11,
        qss=88.0,
        dqs=80.0,
        reliability=75.0,
        quote_timestamp=NOW - timedelta(minutes=30),
        **_LINEAGE,
    )


# ---------------------------------------------------------------------------
# Concurrent test
# ---------------------------------------------------------------------------


def test_select_for_update_blocks_concurrent_writer(pg_engine) -> None:
    """Two sessions race; SELECT FOR UPDATE guarantees one blocks then raises.

    Thread 1 calls persist_accumulator_decision (which acquires FOR UPDATE
    locks on the Prediction rows) but holds the open transaction for 300 ms
    before committing.  Thread 2 starts after Thread 1 signals that its locks
    are held; it calls persist_accumulator_decision and blocks on the same
    FOR UPDATE.  When Thread 1 commits, Thread 2 unblocks, sees
    accumulator_id already set, and raises AccumulatorPersistError.

    The 300 ms hold is short enough to keep the test fast and long enough to
    guarantee Thread 2 reaches its SELECT FOR UPDATE before Thread 1 commits
    (Thread 2 starts immediately on the signal and PostgreSQL's lock wait is
    < 1 ms on a local container).
    """
    # Seed committed data that both sessions will see.
    with Session(pg_engine) as s:
        pairs = _seed_predictions(s, count=6)
        candidates = [_make_qs(f, p, index=i) for i, (f, p) in enumerate(pairs)]
        s.commit()

    decision = build_accumulator_decision(
        candidates,
        as_of=NOW,
        operating_state=OperatingState.NORMAL,
        current_bankroll=1000.0,
        available_bankroll=1000.0,
        committed_daily_exposure=0.0,
    )

    # Sanity check: CORE must find a ticket, otherwise the test is vacuous.
    core_pd = next(pd for pd in decision.products if pd.product is ProductTier.CORE)
    if core_pd.result.ticket is None:
        pytest.skip("CORE ticket not found — pool not qualifying for this test run")

    t1_locks_held = threading.Event()
    t2_error: list[Exception] = []
    t2_success: list[object] = []

    # --- Thread 1: persist + hold the open transaction ---
    def thread1_persist_and_hold() -> None:
        with Session(pg_engine) as s:
            with s.begin():
                persist_accumulator_decision(
                    s,
                    decision=decision,
                    product=ProductTier.CORE,
                    candidates=candidates,
                )
                # Flush happened inside persist_accumulator_decision.
                # The FOR UPDATE locks are now held by this open transaction.
                t1_locks_held.set()
                # Hold the transaction open long enough for Thread 2 to block.
                time.sleep(0.3)
            # Context-manager exit commits → releases locks.

    # --- Thread 2: attempt the same persist while Thread 1 holds the locks ---
    def thread2_attempt() -> None:
        t1_locks_held.wait(timeout=10)
        # Thread 1 is holding the FOR UPDATE locks.  Thread 2 will block here
        # until Thread 1 commits, then unblock and see accumulator_id != None.
        try:
            with Session(pg_engine) as s:
                persist_accumulator_decision(
                    s,
                    decision=decision,
                    product=ProductTier.CORE,
                    candidates=candidates,
                )
                s.commit()
                t2_success.append(True)
        except AccumulatorPersistError as exc:
            t2_error.append(exc)

    t1 = threading.Thread(target=thread1_persist_and_hold)
    t2 = threading.Thread(target=thread2_attempt)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert not t2_success, (
        "Thread 2 should not have succeeded; both sessions claimed the same predictions"
    )
    assert len(t2_error) == 1, f"Expected exactly one AccumulatorPersistError; got {t2_error!r}"
    assert isinstance(t2_error[0], AccumulatorPersistError), (
        f"Expected AccumulatorPersistError, got {type(t2_error[0])!r}: {t2_error[0]}"
    )
