"""Tests for accumulator ticket settlement (backend/services/ticket_settlement.py)."""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Settlement,
    SettlementOutcome,
    Team,
)
from backend.models.settlements import TicketStatus
from backend.services.performance import performance_report
from backend.services.ticket_settlement import (
    _same_price,
    _storable_price,
    settle_decided_tickets,
)
from backend.workers.settlement_worker import run_settlement
from qwantej.performance.accumulator_results import ticket_settlement_odds

NOW = datetime(2026, 9, 27, 20, 0, tzinfo=UTC)
PUBLISHED = NOW - timedelta(hours=10)
KICKOFF = NOW - timedelta(hours=4)


# ---------------------------------------------------------------------------
# Pure settlement price
# ---------------------------------------------------------------------------

class TestTicketSettlementOdds:
    def test_won_ticket_pays_product_of_winning_legs(self) -> None:
        assert ticket_settlement_odds([("win", 1.5), ("win", 2.0)], "won") == pytest.approx(3.0)

    def test_void_legs_drop_out_of_a_won_ticket(self) -> None:
        assert ticket_settlement_odds([("win", 1.5), ("void", 2.0)], "won") == pytest.approx(1.5)

    def test_lost_ticket_recorded_at_full_price(self) -> None:
        legs = [("loss", 1.5), (None, 2.0)]
        assert ticket_settlement_odds(legs, "lost") == pytest.approx(3.0)

    @pytest.mark.parametrize("result", ["void", "pending"])
    def test_undecided_or_void_has_no_price(self, result: str) -> None:
        assert ticket_settlement_odds([("void", 1.5)], result) is None  # type: ignore[arg-type]

    def test_rejects_non_positive_edge_prices(self) -> None:
        with pytest.raises(ValueError):
            ticket_settlement_odds([("win", 1.0)], "won")


# ---------------------------------------------------------------------------
# Service over a real session
# ---------------------------------------------------------------------------

@pytest.fixture(params=["sqlite", "postgres"])
def session(request):
    from backend.core.config import get_settings

    if request.param == "postgres":
        url = get_settings().database_url
        if not url.startswith("postgresql"):
            pytest.skip("ticket correction integration requires migrated test Postgres")
        engine = create_engine(url)
    else:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection) as s:
            yield s
        transaction.rollback()
    engine.dispose()


class _Seeder:
    def __init__(self, session: Session) -> None:
        self.s = session
        self._clock = itertools.count()
        self._comp = Competition(name="EPL")
        self._season = Season(competition=self._comp, label="2026/27")
        session.add_all([self._comp, self._season])
        session.flush()

    def fixture(
        self,
        *,
        status: FixtureStatus = FixtureStatus.FINISHED,
        home_goals: int | None = 2,
        away_goals: int | None = 1,
    ) -> Fixture:
        home, away = Team(name=f"H{uuid.uuid4().hex[:6]}"), Team(name=f"A{uuid.uuid4().hex[:6]}")
        f = Fixture(
            competition=self._comp, season=self._season, home_team=home, away_team=away,
            kickoff_utc=KICKOFF, status=status, home_goals=home_goals, away_goals=away_goals,
        )
        self.s.add_all([home, away, f])
        self.s.flush()
        return f

    def settle(self, prediction_id: uuid.UUID, outcome: str, *, supersedes=None) -> Settlement:
        row = Settlement(
            subject_type="prediction",
            subject_id=prediction_id,
            outcome=SettlementOutcome(outcome),
            settled_at=NOW - timedelta(hours=1) + timedelta(seconds=next(self._clock)),
            supersedes_id=supersedes,
            reason_codes=[],
        )
        self.s.add(row)
        self.s.flush()
        return row

    def ticket(
        self,
        legs: list[str | None],
        *,
        odds: float = 1.8,
        fixture: Fixture | None = None,
        status: TicketStatus = TicketStatus.PENDING,
    ) -> tuple[Accumulator, list[uuid.UUID]]:
        acca = Accumulator(
            product="daily_safe", optimiser_version="v1", policy_version="v1",
            combined_odds=odds ** len(legs), conservative_joint_probability=0.3,
            stressed_joint_probability=0.25, objective_score=0.9,
            dependence_penalty_applied=0.0, published_at=PUBLISHED, status=status,
        )
        self.s.add(acca)
        self.s.flush()
        ids = []
        for idx, outcome in enumerate(legs):
            fx = fixture or self.fixture()
            p = Prediction(
                fixture_id=fx.id, prediction_timestamp=PUBLISHED, decision_as_of=PUBLISHED,
                market="1X2", selection="home", conservative_probability=0.6,
                executable_odds=odds,
            )
            self.s.add(p)
            self.s.flush()
            self.s.add(AccumulatorLeg(
                accumulator_id=acca.id, prediction_id=p.id, leg_index=idx, fixture_id=fx.id,
                league_id="39", market_family="1X2", selection="home", decimal_odds=odds,
                conservative_probability=0.6, edge=0.02, qss=85.0,
            ))
            if outcome is not None:
                self.settle(p.id, outcome)
            ids.append(p.id)
        self.s.flush()
        self.s.expire(acca, ["legs"])
        return acca, ids


def _ticket_rows(session: Session, ticket: Accumulator) -> list[Settlement]:
    return list(session.scalars(
        select(Settlement)
        .where(Settlement.subject_type == "accumulator", Settlement.subject_id == ticket.id)
        .order_by(Settlement.settled_at)
    ))


class TestSettleDecidedTickets:
    def test_all_legs_won_settles_the_ticket_as_won(self, session: Session) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", "win", "win"])
        run = settle_decided_tickets(session, now=NOW)
        assert run.settled == 1
        [row] = _ticket_rows(session, ticket)
        assert row.outcome is SettlementOutcome.WIN
        assert float(row.taken_odds) == pytest.approx(1.8 ** 3, abs=1e-3)
        assert float(row.taken_probability) == pytest.approx(0.3)
        assert row.reason_codes == ["DERIVED_FROM_LEGS"]
        assert ticket.status is TicketStatus.SETTLED

    def test_a_lost_leg_settles_the_ticket_before_other_legs_finish(
        self, session: Session
    ) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["loss", None])
        settle_decided_tickets(session, now=NOW)
        [row] = _ticket_rows(session, ticket)
        assert row.outcome is SettlementOutcome.LOSS
        assert ticket.status is TicketStatus.SETTLED

    def test_undecided_ticket_stays_pending(self, session: Session) -> None:
        # The Postgres concurrency suite commits its own pending ticket;
        # assert this ticket's contribution without assuming an empty DB.
        pending_before = settle_decided_tickets(session, now=NOW).still_pending
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", None])
        run = settle_decided_tickets(session, now=NOW)
        assert run.still_pending == pending_before + 1
        assert _ticket_rows(session, ticket) == []
        assert ticket.status is TicketStatus.PENDING

    def test_void_leg_drops_out_of_the_price(self, session: Session) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", "void"])
        settle_decided_tickets(session, now=NOW)
        [row] = _ticket_rows(session, ticket)
        assert row.outcome is SettlementOutcome.WIN
        assert float(row.taken_odds) == pytest.approx(1.8)

    def test_all_void_legs_settle_as_void_but_stay_correctable(self, session: Session) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["void", "push"])
        settle_decided_tickets(session, now=NOW)
        [row] = _ticket_rows(session, ticket)
        assert row.outcome is SettlementOutcome.VOID
        assert row.taken_odds is None
        # SETTLED, not VOID: VOID is reserved for administratively voided tickets.
        assert ticket.status is TicketStatus.SETTLED

    def test_rerun_is_idempotent(self, session: Session) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", "win"])
        settle_decided_tickets(session, now=NOW)
        run = settle_decided_tickets(session, now=NOW + timedelta(minutes=15))
        assert (run.settled, run.corrected) == (0, 0)
        assert len(_ticket_rows(session, ticket)) == 1

    def test_leg_correction_appends_a_superseding_ticket_settlement(
        self, session: Session
    ) -> None:
        seed = _Seeder(session)
        ticket, legs = seed.ticket(["loss", "win"])
        settle_decided_tickets(session, now=NOW)
        original_leg = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        seed.settle(legs[0], "win", supersedes=original_leg.id)

        run = settle_decided_tickets(session, now=NOW + timedelta(minutes=15))
        assert run.corrected == 1
        first, second = _ticket_rows(session, ticket)
        assert first.outcome is SettlementOutcome.LOSS
        assert second.outcome is SettlementOutcome.WIN
        assert second.supersedes_id == first.id
        assert "LEG_SETTLEMENT_CORRECTED" in second.reason_codes

    def test_administratively_voided_ticket_is_left_alone(self, session: Session) -> None:
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", "win"], status=TicketStatus.VOID)
        settle_decided_tickets(session, now=NOW)
        assert _ticket_rows(session, ticket) == []
        assert ticket.status is TicketStatus.VOID


# ---------------------------------------------------------------------------
# Settlement worker end to end
# ---------------------------------------------------------------------------

class TestWorkerSettlesTickets:
    def test_finished_matches_settle_legs_then_ticket_and_feed_roi(
        self, session: Session
    ) -> None:
        seed = _Seeder(session)
        home_win = seed.fixture(home_goals=2, away_goals=0)
        ticket, _ = seed.ticket([None], odds=2.5, fixture=home_win)

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        assert run.tickets.settled == 1
        assert ticket.status is TicketStatus.SETTLED
        report = performance_report(session, subject_type="accumulator")
        assert report.n_wins == 1
        assert report.stake_basis == "flat_unit"
        assert report.total_profit == pytest.approx(1.5)
        assert report.roi == pytest.approx(1.5)

    def test_cancelled_fixture_voids_its_leg_so_the_ticket_can_settle(
        self, session: Session
    ) -> None:
        seed = _Seeder(session)
        cancelled = seed.fixture(status=FixtureStatus.CANCELLED, home_goals=None, away_goals=None)
        ticket, legs = seed.ticket([None], fixture=cancelled)

        run_settlement(session, now=NOW)

        leg_row = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        assert leg_row.outcome is SettlementOutcome.VOID
        assert leg_row.reason_codes == ["FIXTURE_CANCELLED"]
        [row] = _ticket_rows(session, ticket)
        assert row.outcome is SettlementOutcome.VOID

    def test_fixture_finished_more_than_a_week_ago_still_settles(
        self, session: Session
    ) -> None:
        # Regression: the old 7-day lookback stranded late-arriving results.
        seed = _Seeder(session)
        ticket, _ = seed.ticket([None])
        run = run_settlement(session, now=NOW + timedelta(days=10))
        assert run.total_settled == 1
        assert ticket.status is TicketStatus.SETTLED


# ---------------------------------------------------------------------------
# Review regressions
# ---------------------------------------------------------------------------

class TestReviewRegressions:
    def test_reconciliation_does_not_reload_unchanged_archive(self, session, monkeypatch):
        import backend.services.ticket_settlement as service

        seed = _Seeder(session)
        ticket, legs = seed.ticket(["loss", "win"])
        settle_decided_tickets(session, now=NOW)
        calls = []
        original = service.effective_leg_outcomes

        def capture(db, ids):
            calls.append(ids)
            return original(db, ids)

        monkeypatch.setattr(service, "effective_leg_outcomes", capture)
        settle_decided_tickets(session, now=NOW + timedelta(days=365))
        assert all(set(legs).isdisjoint(ids) for ids in calls)
        old = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        seed.settle(legs[0], "win", supersedes=old.id)
        run = settle_decided_tickets(session, now=NOW + timedelta(days=366))
        assert run.corrected == 1
        assert any(set(legs).issubset(ids) for ids in calls)

    @pytest.mark.parametrize("age", [0, 31, 365])
    def test_reopen_preserves_history_and_removes_loss_until_decided(self, session, age):
        from backend.api.routes.settlements import get_settlement_summary
        from backend.models import AuditEvent
        from backend.services.accumulator_results import accumulator_ticket_records

        seed = _Seeder(session)
        ticket, legs = seed.ticket(["loss", None])
        settle_decided_tickets(session, now=NOW)
        [original] = _ticket_rows(session, ticket)
        leg = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        seed.settle(legs[0], "win", supersedes=leg.id)
        later = NOW + timedelta(days=age, minutes=15)
        settle_decided_tickets(session, now=later)
        assert ticket.status is TicketStatus.PENDING
        assert accumulator_ticket_records(session)[0].result == "pending"
        assert performance_report(session, subject_type="accumulator").n_settled == 0
        assert get_settlement_summary(session, subject_type="accumulator").n_settled == 0
        assert _ticket_rows(session, ticket) == [original]
        assert original.outcome is SettlementOutcome.LOSS
        events = list(session.scalars(select(AuditEvent)))
        assert len(events) == 1
        assert events[0].entity_id == original.id
        settle_decided_tickets(session, now=later + timedelta(minutes=1))
        assert len(list(session.scalars(select(AuditEvent)))) == 1

        # Even a return to the same loss needs a new effective settlement.
        seed.settle(legs[1], "loss")
        settle_decided_tickets(session, now=later + timedelta(minutes=2))
        first, last = _ticket_rows(session, ticket)
        assert last.supersedes_id == first.id
        assert performance_report(session, subject_type="accumulator").n_losses == 1
        assert get_settlement_summary(session, subject_type="accumulator").n_losses == 1
        settle_decided_tickets(session, now=later + timedelta(minutes=3))
        assert len(_ticket_rows(session, ticket)) == 2

    @pytest.mark.parametrize("age", [31, 365])
    def test_old_ticket_correction_is_not_ignored(self, session, age):
        seed = _Seeder(session)
        ticket, legs = seed.ticket(["loss", "win"])
        settle_decided_tickets(session, now=NOW)
        leg = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        seed.settle(legs[0], "win", supersedes=leg.id)
        run = settle_decided_tickets(session, now=NOW + timedelta(days=age))
        assert run.corrected == 1
        assert performance_report(session, subject_type="accumulator").n_wins == 1
        first, last = _ticket_rows(session, ticket)
        assert first.outcome is SettlementOutcome.LOSS
        assert last.supersedes_id == first.id

    def test_half_way_price_rounds_once_and_never_self_corrects(
        self, session: Session
    ) -> None:
        # 1.05 × 1.05 = 1.1025: a half-way value that float rounding and the
        # database's NUMERIC rounding can disagree on.  Rounding once, half-up,
        # must store 1.103 and a rerun must find nothing to correct.
        seed = _Seeder(session)
        ticket, _ = seed.ticket(["win", "win"], odds=1.05)
        settle_decided_tickets(session, now=NOW)
        for minutes in (15, 30, 45):
            run = settle_decided_tickets(session, now=NOW + timedelta(minutes=minutes))
            assert run.corrected == 0
        [row] = _ticket_rows(session, ticket)
        assert Decimal(str(row.taken_odds)) == Decimal("1.103")

    @pytest.mark.parametrize(
        ("stored", "odds", "same"),
        [
            (1.103, 1.1025, True),
            ("1.102", 1.1025, False),
            # 1.01 × 1.05 = 1.0605 exactly, but float rounding gives 1.060 while
            # Postgres stores 1.061 — the case that self-corrected every pass
            # on real Postgres before the fix.
            ("1.061", 1.01 * 1.05, True),
            (None, None, True),
            (2.0, None, False),
        ],
    )
    def test_price_comparison_uses_the_stored_rounding(self, stored, odds, same) -> None:
        assert _same_price(stored, _storable_price(odds)) is same

    def test_result_arriving_late_in_the_polling_window_still_settles(
        self, session: Session
    ) -> None:
        # Fixtures are polled for up to 60 days; settlement must reach as far.
        seed = _Seeder(session)
        ticket, _ = seed.ticket([None])
        run = run_settlement(session, now=KICKOFF + timedelta(days=45))
        assert run.total_settled == 1
        assert ticket.status is TicketStatus.SETTLED

    def test_ticket_settlement_failure_keeps_leg_settlements(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seed = _Seeder(session)
        _, legs = seed.ticket([None])

        def _boom(*_args, **_kwargs):
            raise RuntimeError("simulated ticket settlement bug")

        monkeypatch.setattr("backend.workers.settlement_worker.settle_decided_tickets", _boom)
        run = run_settlement(session, now=NOW)
        assert run.total_settled == 1
        assert run.tickets.errors == ["ticket settlement failed: simulated ticket settlement bug"]
        leg_row = session.scalar(select(Settlement).where(Settlement.subject_id == legs[0]))
        assert leg_row is not None
