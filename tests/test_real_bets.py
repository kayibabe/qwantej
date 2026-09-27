"""Real-money bet tracking: placement rules, settlement → ledger, corrections, API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import (
    Accumulator,
    AccumulatorLeg,
    AuditEvent,
    BankrollLedgerEntry,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    LedgerEntryType,
    Prediction,
    RealBetOutcome,
    Season,
    Team,
    TicketStatus,
)
from backend.services import real_bets as svc
from backend.services.bankroll import current_bankroll

NOW = datetime.now(UTC).replace(microsecond=0)
PUBLISHED = NOW - timedelta(hours=2)
KICKOFF = NOW + timedelta(hours=3)


def _ticket(
    session: Session,
    *,
    status: TicketStatus = TicketStatus.PENDING,
    kickoffs: tuple[datetime, ...] = (KICKOFF, KICKOFF + timedelta(hours=2)),
) -> Accumulator:
    comp = Competition(name=f"League {uuid.uuid4().hex[:6]}")
    season = Season(competition=comp, label="2026/27")
    ticket = Accumulator(
        product="Core", optimiser_version="v1", policy_version="v1",
        combined_odds=3.19, conservative_joint_probability=0.34,
        stressed_joint_probability=0.28, objective_score=0.9,
        dependence_penalty_applied=0, published_at=PUBLISHED, status=status,
    )
    session.add_all([comp, season, ticket])
    session.flush()
    for index, kickoff in enumerate(kickoffs):
        home, away = Team(name=f"H{uuid.uuid4().hex[:6]}"), Team(name=f"A{uuid.uuid4().hex[:6]}")
        fixture = Fixture(competition=comp, season=season, home_team=home, away_team=away,
                          kickoff_utc=kickoff, status=FixtureStatus.SCHEDULED)
        session.add_all([home, away, fixture])
        session.flush()
        prediction = Prediction(
            fixture_id=fixture.id, prediction_timestamp=PUBLISHED, decision_as_of=PUBLISHED,
            market="1X2", selection="home", conservative_probability=0.6, executable_odds=1.8,
        )
        session.add(prediction)
        session.flush()
        session.add(AccumulatorLeg(
            accumulator_id=ticket.id, prediction_id=prediction.id, leg_index=index,
            fixture_id=fixture.id, league_id="39", market_family="1X2", selection="home",
            decimal_odds=1.8, conservative_probability=0.6, edge=0.05, qss=80.0,
        ))
    session.flush()
    return ticket


@pytest.fixture()
def factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def session(factory):
    with factory() as s:
        yield s


def _deposit(session: Session, amount: str = "10000") -> None:
    svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount=amount,
                         occurred_at=PUBLISHED - timedelta(hours=1), now=NOW)


def _bet(session: Session, ticket: Accumulator, **overrides):
    args = dict(accumulator_id=ticket.id, bookmaker="Premier Bet", stake="2500",
                taken_odds="3.10", placed_at=NOW - timedelta(minutes=30), currency="MWK",
                bookmaker_reference=f"SLIP-{uuid.uuid4().hex[:8]}", now=NOW)
    args.update(overrides)
    return svc.place_real_bet(session, **args)


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------

class TestPlacement:
    def test_bet_reserves_stake_without_touching_the_ledger(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        bet = _bet(session, ticket)
        summary = svc.bankroll_summary(session)
        assert summary.currency == "MWK"
        assert summary.balance == Decimal("10000")
        assert summary.open_exposure == Decimal("2500")
        assert summary.available == Decimal("7500")
        assert summary.open_bets == 1
        assert Decimal(str(bet.taken_odds)) == Decimal("3.1")
        ledger_types = session.scalars(select(BankrollLedgerEntry.entry_type)).all()
        assert ledger_types == [LedgerEntryType.DEPOSIT]

    def test_stake_must_fit_available_bankroll(self, session) -> None:
        ticket = _ticket(session)
        with pytest.raises(svc.RealBetError, match="record a deposit first"):
            _bet(session, ticket)
        _deposit(session, "3000")
        _bet(session, ticket, stake="2500")
        with pytest.raises(svc.RealBetError, match="available bankroll of 500"):
            _bet(session, ticket, stake="501")

    def test_currency_must_match_account(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        with pytest.raises(svc.RealBetError, match="kept in MWK"):
            _bet(session, ticket, currency="GBP")

    @pytest.mark.parametrize(
        ("placed_at", "message"),
        [
            (PUBLISHED - timedelta(minutes=1), "before the ticket was published"),
            (NOW + timedelta(hours=1), "cannot be in the future"),
        ],
    )
    def test_placement_time_window(self, session, placed_at, message) -> None:
        ticket = _ticket(session, kickoffs=(KICKOFF, KICKOFF + timedelta(hours=5)))
        _deposit(session)
        with pytest.raises(svc.RealBetError, match=message):
            _bet(session, ticket, placed_at=placed_at)

    def test_uses_earliest_leg_kickoff(self, session) -> None:
        early = NOW - timedelta(minutes=10)
        ticket = _ticket(session, kickoffs=(KICKOFF, early))
        _deposit(session)
        with pytest.raises(svc.RealBetError, match="first kickoff"):
            _bet(session, ticket, placed_at=NOW - timedelta(minutes=5))
        with pytest.raises(svc.RealBetError, match="at or after the first kickoff"):
            _bet(session, ticket, placed_at=early)  # exactly at kickoff
        _bet(session, ticket, placed_at=early - timedelta(seconds=1))  # just before is fine

    def test_naive_timestamp_rejected(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        with pytest.raises(svc.RealBetError, match="time zone"):
            _bet(session, ticket, placed_at=datetime(2026, 9, 27, 10, 0))

    def test_void_and_unknown_tickets(self, session) -> None:
        _deposit(session)
        void_ticket = _ticket(session, status=TicketStatus.VOID)
        with pytest.raises(svc.RealBetError, match="voided"):
            _bet(session, void_ticket)
        with pytest.raises(svc.RealBetNotFound):
            _bet(session, void_ticket, accumulator_id=uuid.uuid4())

    def test_duplicate_slip_reference_rejected(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        _bet(session, ticket, bookmaker_reference="ABC123", stake="100")
        with pytest.raises(svc.RealBetError, match="already recorded"):
            _bet(session, ticket, bookmaker_reference="ABC123", stake="100")

    def test_idempotent_retry_and_key_reuse(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        first = _bet(session, ticket, bookmaker_reference="R1", idempotency_key="bet-key-0001")
        again = _bet(session, ticket, bookmaker_reference="R1", idempotency_key="bet-key-0001")
        assert again.id == first.id
        assert svc.bankroll_summary(session).open_bets == 1
        with pytest.raises(svc.RealBetError, match="different bet"):
            _bet(session, ticket, bookmaker_reference="R1", stake="99",
                 idempotency_key="bet-key-0001")

    def test_placement_is_audited(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session)
        bet = _bet(session, ticket)
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "real_bet_placed")
        ).one()
        assert event.entity_id == bet.id
        assert Decimal(event.payload["published_odds"]) == Decimal("3.19")
        assert event.payload["taken_odds"] == "3.1000"


# --------------------------------------------------------------------------
# Settlement and ledger
# --------------------------------------------------------------------------

class TestSettlement:
    def _open_bet(self, session):
        ticket = _ticket(session)
        _deposit(session)
        return _bet(session, ticket, stake="2500", taken_odds="3.10")

    def test_win_posts_profit_and_frees_exposure(self, session) -> None:
        bet = self._open_bet(session)
        settlement = svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.WON,
                                         payout="7750", settled_at=NOW, now=NOW)
        entry = session.get(BankrollLedgerEntry, settlement.ledger_entry_id)
        assert entry.entry_type is LedgerEntryType.SETTLEMENT
        assert Decimal(str(entry.amount)) == Decimal("5250")
        assert entry.reference == f"real_bet:{bet.id}"
        summary = svc.bankroll_summary(session)
        assert summary.balance == Decimal("15250")
        assert summary.open_exposure == 0
        assert summary.available == Decimal("15250")

    def test_loss_posts_minus_stake(self, session) -> None:
        bet = self._open_bet(session)
        svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.LOST,
                            payout="0", settled_at=NOW, now=NOW)
        assert current_bankroll(session) == Decimal("7500")

    def test_void_returns_stake_without_ledger_entry(self, session) -> None:
        bet = self._open_bet(session)
        s = svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.VOID,
                                payout="2500", settled_at=NOW, now=NOW)
        assert s.ledger_entry_id is None
        assert current_bankroll(session) == Decimal("10000")
        assert svc.bankroll_summary(session).open_exposure == 0

    def test_cash_out_below_stake(self, session) -> None:
        bet = self._open_bet(session)
        svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.CASHED_OUT,
                            payout="1200", settled_at=NOW, now=NOW)
        assert current_bankroll(session) == Decimal("8700")

    @pytest.mark.parametrize(
        ("outcome", "payout", "message"),
        [
            (RealBetOutcome.LOST, "10", "pays out 0"),
            (RealBetOutcome.VOID, "2400", "exactly the stake"),
            (RealBetOutcome.WON, "2500", "more than the stake"),
        ],
    )
    def test_payout_must_match_outcome(self, session, outcome, payout, message) -> None:
        bet = self._open_bet(session)
        with pytest.raises(svc.RealBetError, match=message):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=outcome, payout=payout,
                                settled_at=NOW, now=NOW)

    def test_settled_time_window(self, session) -> None:
        bet = self._open_bet(session)
        with pytest.raises(svc.RealBetError, match="before the bet was placed"):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.LOST, payout="0",
                                settled_at=NOW - timedelta(hours=1), now=NOW)
        with pytest.raises(svc.RealBetError, match="future"):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.LOST, payout="0",
                                settled_at=NOW + timedelta(hours=1), now=NOW)

    def test_second_settlement_requires_correction(self, session) -> None:
        bet = self._open_bet(session)
        first = svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.WON,
                                    payout="7750", settled_at=NOW, now=NOW)
        with pytest.raises(svc.RealBetError, match="already settled"):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.LOST,
                                payout="0", settled_at=NOW, now=NOW)
        with pytest.raises(svc.RealBetError, match="needs a reason"):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.LOST, payout="0",
                                settled_at=NOW, supersedes_id=first.id, now=NOW)

    def test_correction_posts_only_the_difference(self, session) -> None:
        bet = self._open_bet(session)
        first = svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.WON,
                                    payout="7750", settled_at=NOW, now=NOW)
        fix = svc.settle_real_bet(
            session, bet_id=bet.id, outcome=RealBetOutcome.LOST, payout="0", settled_at=NOW,
            supersedes_id=first.id, reason="bookmaker resettled leg 2 as lost", now=NOW,
        )
        delta = session.get(BankrollLedgerEntry, fix.ledger_entry_id)
        assert Decimal(str(delta.amount)) == Decimal("-7750")
        assert current_bankroll(session) == Decimal("7500")  # 10000 - 2500 stake
        session.refresh(bet)
        assert svc.effective_settlement(bet).id == fix.id
        # Superseding a no-longer-current row is refused (no forked history).
        with pytest.raises(svc.RealBetError, match="current settlement"):
            svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.VOID,
                                payout="2500", settled_at=NOW, supersedes_id=first.id,
                                reason="again", now=NOW)

    def test_unknown_bet(self, session) -> None:
        with pytest.raises(svc.RealBetNotFound):
            svc.settle_real_bet(session, bet_id=uuid.uuid4(), outcome=RealBetOutcome.LOST,
                                payout="0", settled_at=NOW, now=NOW)


class TestCashFlows:
    def test_withdrawal_cannot_touch_reserved_stake(self, session) -> None:
        ticket = _ticket(session)
        _deposit(session, "5000")
        _bet(session, ticket, stake="4000")
        with pytest.raises(svc.RealBetError, match="exceeds the available bankroll of 1000"):
            svc.record_cash_flow(session, kind=LedgerEntryType.WITHDRAWAL, amount="1500",
                                 occurred_at=NOW, now=NOW)
        svc.record_cash_flow(session, kind=LedgerEntryType.WITHDRAWAL, amount="1000",
                             occurred_at=NOW, now=NOW)
        assert current_bankroll(session) == Decimal("4000")

    def test_only_positive_amounts(self, session) -> None:
        with pytest.raises(svc.RealBetError, match="greater than zero"):
            svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount="0",
                                 occurred_at=NOW, now=NOW)

    def test_retried_deposit_is_recorded_and_audited_once(self, session) -> None:
        for _ in range(2):
            svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount="500",
                                 occurred_at=NOW, idempotency_key="dep-retry-01", now=NOW)
        assert current_bankroll(session) == Decimal("500")
        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "bankroll_deposit")
        ).all()
        assert len(audits) == 1
        # Same key, different amount: refused, not silently merged.
        with pytest.raises(svc.RealBetError, match="idempotency_key"):
            svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount="501",
                                 occurred_at=NOW, idempotency_key="dep-retry-01", now=NOW)

    @pytest.mark.parametrize("bad", ["abc", "NaN", "Infinity"])
    def test_non_numeric_amounts_rejected(self, session, bad) -> None:
        with pytest.raises(svc.RealBetError, match="number"):
            svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount=bad,
                                 occurred_at=NOW, now=NOW)


# --------------------------------------------------------------------------
# API journey
# --------------------------------------------------------------------------

@pytest.fixture()
def client(factory):
    def _override():
        with factory() as s:
            yield s

    with factory() as seed:
        ticket_id = _ticket(seed).id
        seed.commit()
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c, ticket_id
    app.dependency_overrides.clear()


class TestApi:
    def test_full_journey(self, client) -> None:
        c, ticket_id = client
        r = c.post("/bankroll/deposits", json={
            "amount": "10000", "occurred_at": (NOW - timedelta(hours=3)).isoformat(),
            "reference": "Airtel Money top-up",
        })
        assert r.status_code == 201, r.text
        assert r.json()["balance_after"] == "10000.0000"

        bet_body = {
            "accumulator_id": str(ticket_id), "bookmaker": "Premier Bet",
            "bookmaker_reference": "PB-778812", "currency": "MWK", "stake": "2500",
            "taken_odds": "3.10", "placed_at": (NOW - timedelta(minutes=20)).isoformat(),
        }
        r = c.post("/real-bets", json=bet_body)
        assert r.status_code == 201, r.text
        bet = r.json()
        assert bet["status"] == "open" and bet["settlement"] is None
        assert bet["stake"] == "2500.0000"

        assert c.get("/bankroll").json()["available"] == "7500.0000"
        assert c.get("/real-bets", params={"status": "open"}).json()["total"] == 1

        r = c.post(f"/real-bets/{bet['id']}/settlements", json={
            "outcome": "won", "payout": "7750", "settled_at": NOW.isoformat(),
        })
        assert r.status_code == 201, r.text

        detail = c.get(f"/real-bets/{bet['id']}").json()
        assert detail["status"] == "settled"
        assert detail["profit_loss"] == "5250.0000"
        assert len(detail["history"]) == 1
        assert c.get("/bankroll").json()["balance"] == "15250.0000"
        assert c.get("/real-bets", params={"status": "settled"}).json()["total"] == 1

    def test_rule_violations_are_readable_422s(self, client) -> None:
        c, ticket_id = client
        r = c.post("/real-bets", json={
            "accumulator_id": str(ticket_id), "bookmaker": "Premier Bet", "currency": "MWK",
            "stake": "100", "taken_odds": "3.1", "placed_at": NOW.isoformat(),
        })
        assert r.status_code == 422
        assert "record a deposit first" in r.json()["detail"]

    def test_unknown_fields_and_bad_values_rejected(self, client) -> None:
        c, ticket_id = client
        base = {"accumulator_id": str(ticket_id), "bookmaker": "X", "currency": "MWK",
                "stake": "100", "taken_odds": "3.1", "placed_at": NOW.isoformat()}
        assert c.post("/real-bets", json={**base, "paper_only": False}).status_code == 422
        assert c.post("/real-bets", json={**base, "stake": "-5"}).status_code == 422
        assert c.post("/real-bets", json={**base, "taken_odds": "1.0"}).status_code == 422
        assert c.post("/real-bets", json={**base, "currency": "mwk"}).status_code == 422
        naive = {**base, "placed_at": "2026-09-27T10:00:00"}
        assert c.post("/real-bets", json=naive).status_code == 422

    def test_not_found(self, client) -> None:
        c, _ = client
        assert c.get(f"/real-bets/{uuid.uuid4()}").status_code == 404
        r = c.post(f"/real-bets/{uuid.uuid4()}/settlements", json={
            "outcome": "lost", "payout": "0", "settled_at": NOW.isoformat(),
        })
        assert r.status_code == 404
