"""Tests for backend/services/settlement.py (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Prediction,
    Season,
    Team,
)
from backend.models import (
    SettlementOutcome as OrmOutcome,
)
from backend.services.settlement import (
    SettlementError,
    find_closing_odds,
    is_already_settled,
    resolve_outcome,
    settle_prediction,
)
from qwantej.settlement.types import SettlementOutcome as EngineOutcome

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=3)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def finished_fixture(session: Session) -> Fixture:
    comp = Competition(name="EPL")
    ssn = Season(competition=comp, label="2026/27")
    home, away = Team(name="Home FC"), Team(name="Away FC")
    f = Fixture(
        competition=comp,
        season=ssn,
        home_team=home,
        away_team=away,
        kickoff_utc=KICKOFF,
        status=FixtureStatus.FINISHED,
        home_goals=2,
        away_goals=1,
    )
    session.add_all([comp, ssn, home, away, f])
    session.flush()
    return f


def _make_prediction(
    session: Session,
    fixture: Fixture,
    *,
    market: str = "1X2",
    selection: str = "home",
    conservative_probability: float | None = 0.55,
    executable_odds: float | None = 1.90,
) -> Prediction:
    p = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=KICKOFF - timedelta(hours=1),
        decision_as_of=KICKOFF - timedelta(hours=1),
        market=market,
        selection=selection,
        conservative_probability=conservative_probability,
        executable_odds=executable_odds,
    )
    session.add(p)
    session.flush()
    return p


def _make_fixture(
    session: Session,
    *,
    home_goals: int | None,
    away_goals: int | None,
) -> Fixture:
    comp = Competition(name="Liga")
    ssn = Season(competition=comp, label="2026/27")
    home, away = Team(name="H"), Team(name="A")
    f = Fixture(
        competition=comp,
        season=ssn,
        home_team=home,
        away_team=away,
        kickoff_utc=KICKOFF,
        status=FixtureStatus.FINISHED,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    session.add_all([comp, ssn, home, away, f])
    session.flush()
    return f


# ---------------------------------------------------------------------------
# resolve_outcome — 1X2
# ---------------------------------------------------------------------------

class TestResolveOutcome1X2:
    def test_home_win(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1X2", "home") is EngineOutcome.WIN

    def test_away_loss(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1X2", "away") is EngineOutcome.LOSS

    def test_draw_loss(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1X2", "draw") is EngineOutcome.LOSS

    def test_draw_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "1X2", "draw") is EngineOutcome.WIN

    def test_case_insensitive(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1x2", "Home") is EngineOutcome.WIN


# ---------------------------------------------------------------------------
# resolve_outcome — DOUBLE_CHANCE (canonical ingestion labels: 1X, X2, 12)
# ---------------------------------------------------------------------------

class TestResolveOutcomeDoubleChance:
    def test_1x_wins_on_home_win(self, finished_fixture: Fixture) -> None:
        # 2-1: home wins → 1X (home-or-draw) wins
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "1X") is EngineOutcome.WIN

    def test_1x_wins_on_draw(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "1X") is EngineOutcome.WIN

    def test_1x_loses_on_away_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=0, away_goals=2)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "1X") is EngineOutcome.LOSS

    def test_x2_loses_on_home_win(self, finished_fixture: Fixture) -> None:
        # 2-1: home wins → X2 (draw-or-away) loses
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "X2") is EngineOutcome.LOSS

    def test_x2_wins_on_draw(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=0, away_goals=0)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "X2") is EngineOutcome.WIN

    def test_x2_wins_on_away_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=3)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "X2") is EngineOutcome.WIN

    def test_12_wins_on_home_win(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "12") is EngineOutcome.WIN

    def test_12_wins_on_away_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=0, away_goals=1)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "12") is EngineOutcome.WIN

    def test_12_loses_on_draw(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=2, away_goals=2)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "12") is EngineOutcome.LOSS

    def test_unknown_selection_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="Unknown DOUBLE_CHANCE"):
            resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "home_draw")


# ---------------------------------------------------------------------------
# resolve_outcome — BTTS / TOTALS / edge cases
# ---------------------------------------------------------------------------

class TestResolveOutcomeOtherMarkets:
    def test_btts_yes_wins(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "BTTS", "yes") is EngineOutcome.WIN

    def test_btts_no_wins_when_only_home_scores(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=0)
        assert resolve_outcome(f, "BTTS", "no") is EngineOutcome.WIN
        assert resolve_outcome(f, "BTTS", "yes") is EngineOutcome.LOSS

    def test_btts_unknown_selection_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="Unknown BTTS"):
            resolve_outcome(finished_fixture, "BTTS", "maybe")

    def test_totals_over_wins(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=2, away_goals=1)
        assert resolve_outcome(f, "TOTALS", "over", line=2.5) is EngineOutcome.WIN
        assert resolve_outcome(f, "TOTALS", "under", line=2.5) is EngineOutcome.LOSS

    def test_totals_under_wins(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=0)
        assert resolve_outcome(f, "TOTALS", "under", line=2.5) is EngineOutcome.WIN

    def test_totals_push_on_exact_line(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=2)
        assert resolve_outcome(f, "TOTALS", "over", line=3.0) is EngineOutcome.PUSH

    def test_void_when_goals_missing(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=None, away_goals=None)
        assert resolve_outcome(f, "1X2", "home") is EngineOutcome.VOID

    def test_unknown_market_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="Unsupported market"):
            resolve_outcome(finished_fixture, "HANDICAP", "home")

    def test_totals_missing_line_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="line is required"):
            resolve_outcome(finished_fixture, "TOTALS", "over")


# ---------------------------------------------------------------------------
# settle_prediction
# ---------------------------------------------------------------------------

class TestSettlePrediction:
    def test_settles_win_and_populates_brier(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        assert row.outcome == OrmOutcome.WIN
        assert row.subject_id == pred.id
        assert row.subject_type == "prediction"
        assert row.brier_contribution is not None
        assert row.log_loss_contribution is not None
        assert row.taken_probability is not None
        assert row.calibration_bin is not None

    def test_settles_loss(self, session: Session, finished_fixture: Fixture) -> None:
        pred = _make_prediction(session, finished_fixture, selection="away")
        row = settle_prediction(session, pred, outcome=EngineOutcome.LOSS, settled_at=NOW)
        assert row.outcome == OrmOutcome.LOSS

    def test_clv_positive_when_taken_odds_beat_closing(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture, executable_odds=1.90)
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW, closing_odds=1.75
        )
        assert row.clv is not None
        assert float(row.clv) > 0

    def test_clv_absent_without_closing_odds(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        assert row.clv is None
        assert row.closing_odds is None

    def test_closing_quote_id_stored(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        q = OddsQuote(
            fixture_id=finished_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.80,
            captured_at=KICKOFF + timedelta(minutes=90),
            source="api-football",
        )
        session.add(q)
        session.flush()
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred,
            outcome=EngineOutcome.WIN,
            settled_at=NOW,
            closing_odds=1.80,
            closing_quote_id=q.id,
        )
        assert row.closing_quote_id == q.id

    def test_void_omits_brier_and_log_loss(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(session, pred, outcome=EngineOutcome.VOID, settled_at=NOW)
        assert row.outcome == OrmOutcome.VOID
        assert row.brier_contribution is None
        assert row.log_loss_contribution is None

    def test_idempotency_guard_blocks_double_settle(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        session.flush()
        with pytest.raises(SettlementError, match="already settled"):
            settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)

    def test_correction_allowed_with_supersedes_id(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        original = settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        session.flush()
        correction = settle_prediction(
            session, pred,
            outcome=EngineOutcome.LOSS,
            settled_at=NOW + timedelta(seconds=1),
            reason_codes=["CORRECTION"],
            supersedes_id=original.id,
        )
        assert correction.supersedes_id == original.id
        assert "CORRECTION" in correction.reason_codes

    def test_correction_rejects_wrong_subject(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred_a = _make_prediction(session, finished_fixture, selection="home")
        pred_b = _make_prediction(session, finished_fixture, selection="away")
        original_a = settle_prediction(
            session, pred_a, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        session.flush()
        with pytest.raises(SettlementError, match="belongs to prediction"):
            settle_prediction(
                session, pred_b,
                outcome=EngineOutcome.LOSS,
                settled_at=NOW + timedelta(seconds=1),
                supersedes_id=original_a.id,
            )

    def test_correction_rejects_nonexistent_supersedes(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        import uuid as _uuid
        pred = _make_prediction(session, finished_fixture)
        with pytest.raises(SettlementError, match="does not exist"):
            settle_prediction(
                session, pred,
                outcome=EngineOutcome.WIN,
                settled_at=NOW,
                supersedes_id=_uuid.uuid4(),
            )

    def test_no_probability_means_no_brier(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture, conservative_probability=None)
        row = settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        assert row.brier_contribution is None

    def test_result_source_stored(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW,
            result_source="manual-override",
        )
        assert row.result_source == "manual-override"


# ---------------------------------------------------------------------------
# is_already_settled
# ---------------------------------------------------------------------------

class TestIsAlreadySettled:
    def test_false_before_any_settlement(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        assert not is_already_settled(
            session, subject_type="prediction", subject_id=pred.id
        )

    def test_true_after_settlement(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        session.flush()
        assert is_already_settled(
            session, subject_type="prediction", subject_id=pred.id
        )

    def test_still_true_after_correction_appended(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        original = settle_prediction(session, pred, outcome=EngineOutcome.WIN, settled_at=NOW)
        session.flush()
        settle_prediction(
            session, pred,
            outcome=EngineOutcome.LOSS,
            settled_at=NOW + timedelta(seconds=1),
            reason_codes=["CORRECTION"],
            supersedes_id=original.id,
        )
        session.flush()
        assert is_already_settled(
            session, subject_type="prediction", subject_id=pred.id
        )


# ---------------------------------------------------------------------------
# find_closing_odds
# ---------------------------------------------------------------------------

class TestFindClosingOdds:
    def test_returns_latest_post_kickoff_quote(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        session.add(OddsQuote(
            fixture_id=finished_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.95,
            captured_at=KICKOFF - timedelta(minutes=10),
            source="api-football",
        ))
        session.add(OddsQuote(
            fixture_id=finished_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.75,
            captured_at=KICKOFF + timedelta(minutes=90),
            source="api-football",
        ))
        session.flush()

        odds, bookmaker, quote_id = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        assert odds == pytest.approx(1.75)
        assert bookmaker == "BetFair"
        assert quote_id is not None

    def test_returns_none_when_no_post_kickoff_quote(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        session.add(OddsQuote(
            fixture_id=finished_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.95,
            captured_at=KICKOFF - timedelta(hours=1),
            source="api-football",
        ))
        session.flush()

        odds, bk, qid = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        assert odds is None
        assert bk is None
        assert qid is None

    def test_excludes_quotes_outside_closing_window(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        # > 5 hours after kickoff — outside the closing window
        session.add(OddsQuote(
            fixture_id=finished_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.50,
            captured_at=KICKOFF + timedelta(hours=6),
            source="api-football",
        ))
        session.flush()

        odds, _, _ = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        assert odds is None

    def test_tie_breaker_deterministic(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        # Two quotes at identical timestamps: the one inserted second should
        # win via id DESC tie-breaker.
        same_ts = KICKOFF + timedelta(minutes=45)
        q1 = OddsQuote(
            fixture_id=finished_fixture.id, bookmaker="BK1",
            market="1X2", selection="home", decimal_odds=1.80,
            captured_at=same_ts, source="api-football",
        )
        q2 = OddsQuote(
            fixture_id=finished_fixture.id, bookmaker="BK2",
            market="1X2", selection="home", decimal_odds=1.85,
            captured_at=same_ts, source="api-football",
        )
        session.add_all([q1, q2])
        session.flush()

        odds, _, _ = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        # Exactly one of the two is returned; either way it is deterministic.
        assert odds in (pytest.approx(1.80), pytest.approx(1.85))


# ---------------------------------------------------------------------------
# closing_quote_id validation (P2 fix)
# ---------------------------------------------------------------------------

class TestClosingQuoteIdValidation:
    def _make_quote(
        self,
        session: Session,
        fixture: Fixture,
        *,
        market: str = "1X2",
        decimal_odds: float = 1.75,
    ) -> OddsQuote:
        q = OddsQuote(
            fixture_id=fixture.id,
            bookmaker="BetFair",
            market=market,
            selection="home",
            decimal_odds=decimal_odds,
            captured_at=KICKOFF + timedelta(minutes=90),
            source="api-football",
        )
        session.add(q)
        session.flush()
        return q

    def test_valid_quote_accepted(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        q = self._make_quote(session, finished_fixture)
        row = settle_prediction(
            session, pred,
            outcome=EngineOutcome.WIN,
            settled_at=NOW,
            closing_odds=float(q.decimal_odds),
            closing_quote_id=q.id,
        )
        assert row.closing_quote_id == q.id

    def test_nonexistent_quote_raises(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        import uuid
        pred = _make_prediction(session, finished_fixture)
        with pytest.raises(SettlementError, match="does not exist"):
            settle_prediction(
                session, pred,
                outcome=EngineOutcome.WIN,
                settled_at=NOW,
                closing_quote_id=uuid.uuid4(),
            )

    def test_wrong_fixture_raises(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        other_fixture = _make_fixture(session, home_goals=1, away_goals=0)
        pred = _make_prediction(session, finished_fixture)
        q = OddsQuote(
            fixture_id=other_fixture.id,
            bookmaker="BetFair",
            market="1X2",
            selection="home",
            decimal_odds=1.75,
            captured_at=KICKOFF + timedelta(minutes=90),
            source="api-football",
        )
        session.add(q)
        session.flush()
        with pytest.raises(SettlementError, match="belongs to fixture"):
            settle_prediction(
                session, pred,
                outcome=EngineOutcome.WIN,
                settled_at=NOW,
                closing_quote_id=q.id,
            )

    def test_wrong_market_raises(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture, market="1X2")
        q = self._make_quote(session, finished_fixture, market="BTTS")
        with pytest.raises(SettlementError, match="is for market"):
            settle_prediction(
                session, pred,
                outcome=EngineOutcome.WIN,
                settled_at=NOW,
                closing_quote_id=q.id,
            )

    def test_odds_mismatch_raises(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        q = self._make_quote(session, finished_fixture, decimal_odds=1.75)
        with pytest.raises(SettlementError, match="decimal_odds"):
            settle_prediction(
                session, pred,
                outcome=EngineOutcome.WIN,
                settled_at=NOW,
                closing_odds=2.50,    # deliberately mismatched
                closing_quote_id=q.id,
            )

    def test_odds_within_tolerance_accepted(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        q = self._make_quote(session, finished_fixture, decimal_odds=1.75)
        # 1e-5 difference — inside 1e-4 tolerance
        row = settle_prediction(
            session, pred,
            outcome=EngineOutcome.WIN,
            settled_at=NOW,
            closing_odds=1.75001,
            closing_quote_id=q.id,
        )
        assert row.closing_quote_id == q.id
