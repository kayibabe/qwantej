"""Tests for backend/services/performance.py (framework §39, §40)."""

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
    Prediction,
    Season,
    Team,
)
from backend.models.settlements import Settlement, SettlementOutcome
from backend.services.performance import (
    performance_by_segment,
    performance_report,
    query_performance_observations,
)
from qwantej.performance.kpi import KPIReport, PerformanceObservation

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=3)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_fixture(
    session: Session,
    *,
    league: str = "EPL",
) -> Fixture:
    comp = Competition(name=league)
    ssn = Season(competition=comp, label="2026/27")
    home, away = Team(name="H"), Team(name="A")
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
) -> Prediction:
    p = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=KICKOFF - timedelta(hours=1),
        decision_as_of=KICKOFF - timedelta(hours=1),
        market=market,
        selection="home",
        conservative_probability=0.55,
        executable_odds=1.90,
    )
    session.add(p)
    session.flush()
    return p


def _make_settlement(
    session: Session,
    prediction: Prediction,
    *,
    outcome: SettlementOutcome = SettlementOutcome.WIN,
    brier: float | None = 0.20,
    log_loss: float | None = 0.51,
    clv: float | None = 0.03,
    taken_odds: float | None = 1.90,
    stake: float | None = None,
    profit_loss: float | None = None,
    settled_at: datetime = NOW,
    supersedes_id=None,
) -> Settlement:
    s = Settlement(
        subject_type="prediction",
        subject_id=prediction.id,
        outcome=outcome,
        settled_at=settled_at,
        brier_contribution=brier,
        log_loss_contribution=log_loss,
        clv=clv,
        taken_odds=taken_odds,
        taken_probability=0.55,
        stake=stake,
        profit_loss=profit_loss,
        supersedes_id=supersedes_id,
    )
    session.add(s)
    session.flush()
    return s


# ---------------------------------------------------------------------------
# query_performance_observations
# ---------------------------------------------------------------------------

class TestQueryPerformanceObservations:
    def test_returns_empty_when_no_settlements(self, session: Session) -> None:
        obs = query_performance_observations(session)
        assert obs == []

    def test_returns_one_observation(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p)
        obs = query_performance_observations(session)
        assert len(obs) == 1
        assert isinstance(obs[0], PerformanceObservation)

    def test_outcome_mapped_correctly(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p, outcome=SettlementOutcome.LOSS)
        obs = query_performance_observations(session)
        assert obs[0].outcome == "loss"

    def test_market_populated_from_prediction(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p)
        obs = query_performance_observations(session)
        assert obs[0].market == "BTTS"

    def test_league_populated_from_competition(self, session: Session) -> None:
        f = _make_fixture(session, league="La Liga")
        p = _make_prediction(session, f)
        _make_settlement(session, p)
        obs = query_performance_observations(session)
        assert obs[0].league == "La Liga"

    def test_clv_populated(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p, clv=0.05)
        obs = query_performance_observations(session)
        assert obs[0].clv == pytest.approx(0.05)

    def test_brier_and_log_loss_populated(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p, brier=0.16, log_loss=0.51)
        obs = query_performance_observations(session)
        assert obs[0].brier_contribution == pytest.approx(0.16)
        assert obs[0].log_loss_contribution == pytest.approx(0.51)

    def test_excludes_superseded_rows(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        original = _make_settlement(session, p, outcome=SettlementOutcome.WIN)
        session.flush()
        # Correction supersedes the original
        _make_settlement(
            session, p,
            outcome=SettlementOutcome.LOSS,
            settled_at=NOW + timedelta(seconds=1),
            supersedes_id=original.id,
        )
        session.flush()
        obs = query_performance_observations(session)
        # Only the correction (LOSS) should appear; the original (WIN) is superseded.
        assert len(obs) == 1
        assert obs[0].outcome == "loss"

    def test_since_filter(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1, settled_at=NOW - timedelta(days=2))
        _make_settlement(session, p2, settled_at=NOW)
        obs = query_performance_observations(session, since=NOW - timedelta(hours=1))
        assert len(obs) == 1
        assert obs[0].market == "BTTS"

    def test_market_filter(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1)
        _make_settlement(session, p2)
        obs = query_performance_observations(session, market="1X2")
        assert len(obs) == 1
        assert obs[0].market == "1X2"

    def test_staked_fields_populated(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p, stake=10.0, profit_loss=9.0)
        obs = query_performance_observations(session)
        assert obs[0].stake == pytest.approx(10.0)
        assert obs[0].profit_loss == pytest.approx(9.0)

    def test_taken_probability_populated(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p)  # _make_settlement always stores taken_probability=0.55
        obs = query_performance_observations(session)
        assert obs[0].taken_probability == pytest.approx(0.55)

    def test_ordering_is_deterministic_same_timestamp(self, session: Session) -> None:
        # Both settlements share the same settled_at; order must be stable by id.
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1, outcome=SettlementOutcome.WIN, settled_at=NOW)
        _make_settlement(session, p2, outcome=SettlementOutcome.LOSS, settled_at=NOW)
        obs1 = query_performance_observations(session)
        obs2 = query_performance_observations(session)
        # Order must be identical across two calls
        assert [o.market for o in obs1] == [o.market for o in obs2]


# ---------------------------------------------------------------------------
# performance_report
# ---------------------------------------------------------------------------

class TestPerformanceReport:
    def test_returns_kpi_report(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p)
        report = performance_report(session)
        assert isinstance(report, KPIReport)

    def test_empty_returns_zero_counts(self, session: Session) -> None:
        report = performance_report(session)
        assert report.n_total == 0
        assert report.hit_rate is None

    def test_hit_rate_computed(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1, outcome=SettlementOutcome.WIN)
        _make_settlement(session, p2, outcome=SettlementOutcome.LOSS)
        report = performance_report(session)
        assert report.hit_rate == pytest.approx(0.5)

    def test_mean_clv_aggregated(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1, clv=0.04)
        _make_settlement(session, p2, clv=0.02)
        report = performance_report(session)
        assert report.mean_clv == pytest.approx(0.03)

    def test_brier_score_aggregated(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        _make_settlement(session, p1, brier=0.20)
        _make_settlement(session, p2, brier=0.10)
        report = performance_report(session)
        assert report.brier_score == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# performance_by_segment
# ---------------------------------------------------------------------------

class TestPerformanceBySegment:
    def test_segment_by_market(self, session: Session) -> None:
        f = _make_fixture(session)
        p1 = _make_prediction(session, f, market="1X2")
        p2 = _make_prediction(session, f, market="BTTS")
        p3 = _make_prediction(session, f, market="1X2")
        _make_settlement(session, p1, outcome=SettlementOutcome.WIN)
        _make_settlement(session, p2, outcome=SettlementOutcome.LOSS)
        _make_settlement(session, p3, outcome=SettlementOutcome.LOSS)
        result = performance_by_segment(session, by="market")
        assert "1X2" in result
        assert "BTTS" in result
        assert result["1X2"].n_total == 2
        assert result["BTTS"].n_total == 1

    def test_segment_by_league(self, session: Session) -> None:
        f_epl = _make_fixture(session, league="EPL")
        f_la = _make_fixture(session, league="La Liga")
        p1 = _make_prediction(session, f_epl)
        p2 = _make_prediction(session, f_la)
        _make_settlement(session, p1, outcome=SettlementOutcome.WIN)
        _make_settlement(session, p2, outcome=SettlementOutcome.LOSS)
        result = performance_by_segment(session, by="league")
        assert result["EPL"].n_wins == 1
        assert result["La Liga"].n_losses == 1

    def test_segment_returns_kpi_reports(self, session: Session) -> None:
        f = _make_fixture(session)
        p = _make_prediction(session, f)
        _make_settlement(session, p)
        result = performance_by_segment(session, by="market")
        for report in result.values():
            assert isinstance(report, KPIReport)
