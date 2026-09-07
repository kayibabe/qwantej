"""Tests for backend/services/settlement.py (Phase 10)."""

from __future__ import annotations

import uuid
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
    Settlement,
    SettlementOutcome as OrmOutcome,
    Team,
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
    conservative_probability: float = 0.55,
    executable_odds: float = 1.90,
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
# resolve_outcome
# ---------------------------------------------------------------------------

class TestResolveOutcome:
    def test_1x2_home_win(self, finished_fixture: Fixture) -> None:
        # 2-1: home wins
        assert resolve_outcome(finished_fixture, "1X2", "home") is EngineOutcome.WIN

    def test_1x2_away_loss(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1X2", "away") is EngineOutcome.LOSS

    def test_1x2_draw_loss(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1X2", "draw") is EngineOutcome.LOSS

    def test_1x2_draw_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "1X2", "draw") is EngineOutcome.WIN

    def test_double_chance_home_draw_win_on_home_win(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "home_draw") is EngineOutcome.WIN

    def test_double_chance_draw_away_loss_on_home_win(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "draw_away") is EngineOutcome.LOSS

    def test_double_chance_home_away_win_on_decisive(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "home_away") is EngineOutcome.WIN

    def test_double_chance_home_away_loss_on_draw(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "DOUBLE_CHANCE", "home_away") is EngineOutcome.LOSS

    def test_btts_yes_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        assert resolve_outcome(f, "BTTS", "yes") is EngineOutcome.WIN

    def test_btts_no_win_when_only_home_scores(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=0)
        assert resolve_outcome(f, "BTTS", "no") is EngineOutcome.WIN
        assert resolve_outcome(f, "BTTS", "yes") is EngineOutcome.LOSS

    def test_totals_over_wins(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=2, away_goals=1)  # 3 goals
        assert resolve_outcome(f, "TOTALS", "over", line=2.5) is EngineOutcome.WIN
        assert resolve_outcome(f, "TOTALS", "under", line=2.5) is EngineOutcome.LOSS

    def test_totals_under_wins(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=0)  # 1 goal
        assert resolve_outcome(f, "TOTALS", "under", line=2.5) is EngineOutcome.WIN

    def test_totals_push_on_exact_line(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=2)  # 3 goals
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

    def test_unknown_double_chance_selection_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="Unknown DOUBLE_CHANCE"):
            resolve_outcome(finished_fixture, "DOUBLE_CHANCE", "bogus")

    def test_unknown_btts_selection_raises(self, finished_fixture: Fixture) -> None:
        with pytest.raises(SettlementError, match="Unknown BTTS"):
            resolve_outcome(finished_fixture, "BTTS", "maybe")

    def test_case_insensitive_market_and_selection(self, finished_fixture: Fixture) -> None:
        assert resolve_outcome(finished_fixture, "1x2", "Home") is EngineOutcome.WIN


# ---------------------------------------------------------------------------
# settle_prediction
# ---------------------------------------------------------------------------

class TestSettlePrediction:
    def test_settles_win_and_populates_brier(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        assert row.outcome == OrmOutcome.WIN
        assert row.subject_id == pred.id
        assert row.subject_type == "prediction"
        assert row.brier_contribution is not None
        assert row.log_loss_contribution is not None
        assert row.taken_probability is not None
        assert row.calibration_bin is not None

    def test_settles_loss(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture, selection="away")
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.LOSS, settled_at=NOW
        )
        assert row.outcome == OrmOutcome.LOSS

    def test_clv_positive_when_taken_odds_beat_closing(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        # taken=1.90, closing=1.75 → positive CLV (beat the line)
        pred = _make_prediction(session, finished_fixture, executable_odds=1.90)
        row = settle_prediction(
            session, pred,
            outcome=EngineOutcome.WIN,
            settled_at=NOW,
            closing_odds=1.75,
        )
        assert row.clv is not None
        assert float(row.clv) > 0

    def test_clv_absent_without_closing_odds(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        assert row.clv is None
        assert row.closing_odds is None

    def test_void_omits_brier_and_log_loss(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.VOID, settled_at=NOW
        )
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
        from datetime import timedelta

        pred = _make_prediction(session, finished_fixture)
        original = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        session.flush()
        correction = settle_prediction(
            session,
            pred,
            outcome=EngineOutcome.LOSS,
            settled_at=NOW + timedelta(seconds=1),
            reason_codes=["CORRECTION"],
            supersedes_id=original.id,
        )
        assert correction.supersedes_id == original.id
        assert "CORRECTION" in correction.reason_codes

    def test_no_probability_means_no_brier(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(
            session, finished_fixture, conservative_probability=None
        )
        row = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        assert row.brier_contribution is None

    def test_result_source_stored(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        pred = _make_prediction(session, finished_fixture)
        row = settle_prediction(
            session, pred,
            outcome=EngineOutcome.WIN,
            settled_at=NOW,
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
        from datetime import timedelta

        pred = _make_prediction(session, finished_fixture)
        original = settle_prediction(
            session, pred, outcome=EngineOutcome.WIN, settled_at=NOW
        )
        session.flush()
        settle_prediction(
            session,
            pred,
            outcome=EngineOutcome.LOSS,
            settled_at=NOW + timedelta(seconds=1),  # distinct ts to satisfy unique constraint
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
        # Pre-kickoff quote — should be excluded.
        session.add(
            OddsQuote(
                fixture_id=finished_fixture.id,
                bookmaker="BetFair",
                market="1X2",
                selection="home",
                decimal_odds=1.95,
                captured_at=KICKOFF - timedelta(minutes=10),
                source="api-football",
            )
        )
        # Post-kickoff closing quote.
        session.add(
            OddsQuote(
                fixture_id=finished_fixture.id,
                bookmaker="BetFair",
                market="1X2",
                selection="home",
                decimal_odds=1.75,
                captured_at=KICKOFF + timedelta(minutes=90),
                source="api-football",
            )
        )
        session.flush()

        odds, bookmaker = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        assert odds == pytest.approx(1.75)
        assert bookmaker == "BetFair"

    def test_returns_none_when_no_post_kickoff_quote(
        self, session: Session, finished_fixture: Fixture
    ) -> None:
        session.add(
            OddsQuote(
                fixture_id=finished_fixture.id,
                bookmaker="BetFair",
                market="1X2",
                selection="home",
                decimal_odds=1.95,
                captured_at=KICKOFF - timedelta(hours=1),
                source="api-football",
            )
        )
        session.flush()

        odds, bk = find_closing_odds(
            session,
            fixture_id=finished_fixture.id,
            market="1X2",
            selection="home",
            line=None,
            after=KICKOFF,
        )
        assert odds is None
        assert bk is None
