"""Daily market hit-rate and ROI scan using point-in-time prices."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import CAT, cat_day_bounds_utc, settings
from app.models.match import Match, MatchStatus
from app.models.prediction import Prediction
from app.models.research import SelectionResult
from app.services.performance import _as_utc, _has_pre_kickoff_information
from app.services.settlement import evaluate_selection


HIT_RATE_THRESHOLD = 0.50
ROI_THRESHOLD = 0.30
MIN_Q_SCORE = 70
MIN_DECIMAL_ODDS = 2.0
MAX_DECIMAL_ODDS = 3.0
MAX_QUOTE_AGE = timedelta(hours=3)


def _fresh_pre_kickoff_prediction(
    prediction: Prediction, now: datetime, *, require_current_freshness: bool = False
) -> bool:
    match = prediction.match
    provenance = prediction.source_odds_provenance or {}
    if (
        match is None
        or prediction.source_odds_id is None
        or not provenance.get("bookmaker")
        or provenance.get("is_fallback") is True
    ):
        return False
    if prediction.source_decimal_odds is None or prediction.source_decimal_odds <= 1:
        return False
    if prediction.source_odds_at is None or not _has_pre_kickoff_information(prediction):
        return False

    quote_at = _as_utc(prediction.source_odds_at)
    kickoff_at = _as_utc(match.kickoff_at)
    information_at = _as_utc(prediction.decision_at or prediction.as_of_at or prediction.created_at)
    max_age = timedelta(hours=settings.max_selection_odds_age_hours)
    quote_age_at_decision = information_at - quote_at
    valid = (
        quote_at < kickoff_at
        and information_at < kickoff_at
        and quote_at <= information_at
        and timedelta(0) <= quote_age_at_decision <= max_age
    )
    if require_current_freshness:
        valid = valid and timedelta(0) <= _as_utc(now) - quote_at <= max_age
    return valid


async def daily_market_roi(db: AsyncSession, target_date: date | None = None) -> dict:
    """Evaluate prior settled predictions and find today's matching candidates.

    Each historical fixture/market/selection is counted once from its latest
    valid pre-kickoff prediction with captured bookmaker pricing. A flat unit
    stake at that decimal price is used to calculate ROI. Today's rows are a
    research shortlist only.
    """
    now = datetime.now(timezone.utc)
    target_date = target_date or now.astimezone(CAT).date()
    day_start, day_end = cat_day_bounds_utc(target_date)

    history_result = await db.execute(
        select(Prediction)
        .join(Match, Match.id == Prediction.match_id)
        .options(joinedload(Prediction.match))
        .where(
            Match.kickoff_at < day_start,
            Match.status == MatchStatus.FINISHED,
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
            Prediction.q_score >= MIN_Q_SCORE,
            Prediction.source_odds_id.is_not(None),
            Prediction.source_odds_at.is_not(None),
            Prediction.source_decimal_odds >= MIN_DECIMAL_ODDS,
            Prediction.source_decimal_odds < MAX_DECIMAL_ODDS,
        )
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
    )

    # Keep one latest valid pre-kickoff prediction for each historical
    # fixture/market/selection, independent of whether it appeared on a ticket.
    unique_history: dict[tuple[int, str, str], tuple[Prediction, SelectionResult]] = {}
    unsupported = 0
    for prediction in history_result.scalars().all():
        match = prediction.match
        if match is None:
            continue
        if (
            prediction.q_score < MIN_Q_SCORE
            or prediction.source_decimal_odds is None
            or not MIN_DECIMAL_ODDS <= prediction.source_decimal_odds < MAX_DECIMAL_ODDS
            or not _fresh_pre_kickoff_prediction(prediction, now)
        ):
            continue
        quote_age = _as_utc(prediction.decision_at or prediction.as_of_at or prediction.created_at) - _as_utc(prediction.source_odds_at)
        if quote_age > MAX_QUOTE_AGE:
            continue
        key = (prediction.match_id, prediction.market, prediction.selection)
        if key in unique_history:
            continue
        try:
            outcome = evaluate_selection(prediction.selection, match.home_goals, match.away_goals)
        except ValueError:
            try:
                outcome = evaluate_selection(prediction.market, match.home_goals, match.away_goals)
            except ValueError:
                unsupported += 1
                continue
        if outcome in (SelectionResult.WON, SelectionResult.LOST):
            unique_history[key] = (prediction, outcome)

    cohorts: dict[str, list[tuple[Prediction, SelectionResult]]] = defaultdict(list)
    fixture_outcomes: dict[int, list[SelectionResult]] = defaultdict(list)
    for (match_id, market, _selection), (prediction, outcome) in unique_history.items():
        cohorts[market].append((prediction, outcome))
        fixture_outcomes[match_id].append(outcome)

    market_rows = []
    for market, items in cohorts.items():
        wins = sum(result == SelectionResult.WON for _, result in items)
        losses = len(items) - wins
        pnl = sum(
            prediction.source_decimal_odds - 1
            if result == SelectionResult.WON
            else -1
            for prediction, result in items
        )
        roi = pnl / len(items)
        hit_rate = wins / len(items)
        market_rows.append({
            "market": market,
            "sample_size": len(items),
            "wins": wins,
            "losses": losses,
            "hit_rate": hit_rate,
            "flat_stake_pnl": pnl,
            "roi": roi,
            "average_odds": sum(prediction.source_decimal_odds for prediction, _result in items) / len(items),
            "qualifies": hit_rate > HIT_RATE_THRESHOLD and roi > ROI_THRESHOLD,
            "evidence_label": "very small sample" if len(items) < 10 else "small sample" if len(items) < 30 else "larger sample",
        })
    market_rows.sort(key=lambda row: (-row["roi"], -row["sample_size"], row["market"]))
    qualifying_markets = {row["market"] for row in market_rows if row["qualifies"]}
    fixture_summary = {
        "unique_fixtures": len(fixture_outcomes),
        "all_won": sum(all(result == SelectionResult.WON for result in outcomes) for outcomes in fixture_outcomes.values()),
        "all_lost": sum(all(result == SelectionResult.LOST for result in outcomes) for outcomes in fixture_outcomes.values()),
        "mixed": sum(
            any(result == SelectionResult.WON for result in outcomes)
            and any(result == SelectionResult.LOST for result in outcomes)
            for outcomes in fixture_outcomes.values()
        ),
    }

    today_result = await db.execute(
        select(Prediction)
        .join(Match, Prediction.match_id == Match.id)
        .options(
            joinedload(Prediction.match)
            .joinedload(Match.home_team),
            joinedload(Prediction.match)
            .joinedload(Match.away_team),
            joinedload(Prediction.match)
            .joinedload(Match.competition),
        )
        .where(Match.kickoff_at >= day_start, Match.kickoff_at < day_end)
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
    )

    today_latest: dict[tuple[int, str, str], Prediction] = {}
    for prediction in today_result.scalars().all():
        match = prediction.match
        status = getattr(match.status, "value", match.status) if match else None
        if match is None or status not in {"scheduled", "live", "finished", "postponed", "cancelled"}:
            continue
        key = (prediction.match_id, prediction.market, prediction.selection)
        if key in today_latest or prediction.market not in qualifying_markets:
            continue
        # Keep the historical point-in-time price if it was fresh when the
        # prediction was made. Its age at refresh is informational; it must not
        # erase a day's already selected matches from the daily report.
        if not _fresh_pre_kickoff_prediction(prediction, now):
            continue
        quote_age_now = _as_utc(now) - _as_utc(prediction.source_odds_at)
        if (
            prediction.q_score < MIN_Q_SCORE
            or prediction.source_decimal_odds is None
            or not MIN_DECIMAL_ODDS <= prediction.source_decimal_odds < MAX_DECIMAL_ODDS
        ):
            continue
        today_latest[key] = prediction

    roi_by_market = {row["market"]: row for row in market_rows}
    candidates = []
    for prediction in today_latest.values():
        match = prediction.match
        quote_at = _as_utc(prediction.source_odds_at)
        match_status = getattr(match.status, "value", match.status)
        result = None
        if match_status in {"postponed", "cancelled"}:
            result = SelectionResult.VOID.value
        elif match_status == "finished" and match.home_goals is not None and match.away_goals is not None:
            try:
                result = evaluate_selection(prediction.selection, match.home_goals, match.away_goals).value
            except ValueError:
                try:
                    result = evaluate_selection(prediction.market, match.home_goals, match.away_goals).value
                except ValueError:
                    result = None
        candidates.append({
            "prediction_id": prediction.id,
            "match_id": match.id,
            "home_team": match.home_team.name if match.home_team else "Home",
            "away_team": match.away_team.name if match.away_team else "Away",
            "competition": match.competition.name if match.competition else "",
            "kickoff_at": _as_utc(match.kickoff_at).isoformat(),
            "match_status": match_status,
            "home_goals": match.home_goals,
            "away_goals": match.away_goals,
            "result": result,
            "market": prediction.market,
            "selection": prediction.selection,
            "odds": prediction.source_decimal_odds,
            "model_probability": prediction.model_probability,
            "q_score": prediction.q_score,
            "q_grade": prediction.q_grade.value if hasattr(prediction.q_grade, "value") else str(prediction.q_grade),
            "recommendation_status": prediction.recommendation_status,
            "market_roi": roi_by_market[prediction.market]["roi"],
            "market_hit_rate": roi_by_market[prediction.market]["hit_rate"],
            "market_sample_size": roi_by_market[prediction.market]["sample_size"],
            "bookmaker": (prediction.source_odds_provenance or {}).get("bookmaker"),
            "quote_at": quote_at.isoformat(),
            "quote_age_minutes": max(0.0, (now - quote_at).total_seconds() / 60),
        })
    candidates.sort(key=lambda row: (row["kickoff_at"], -row["market_roi"], row["match_id"], row["market"], row["selection"]))

    return {
        "target_date": target_date.isoformat(),
        "refreshed_at": now.isoformat(),
        "roi_threshold": ROI_THRESHOLD,
        "hit_rate_threshold": HIT_RATE_THRESHOLD,
        "min_q_score": MIN_Q_SCORE,
        "min_decimal_odds": MIN_DECIMAL_ODDS,
        "max_decimal_odds_exclusive": MAX_DECIMAL_ODDS,
        "max_quote_age_hours": MAX_QUOTE_AGE.total_seconds() / 3600,
        "historical_through": (target_date - timedelta(days=1)).isoformat(),
        "historical_unique_selections": sum(row["sample_size"] for row in market_rows),
        "historical_fixture_summary": fixture_summary,
        "historical_markets": market_rows,
        "qualifying_markets": sorted(qualifying_markets),
        "candidate_count": len(candidates),
        "candidate_fixture_count": len({row["match_id"] for row in candidates}),
        "candidates": candidates,
        "unsupported_outcomes_excluded": unsupported,
        "method": "Historical hit rate and flat one-unit ROI use the latest valid pre-kickoff prediction per unique fixture-market-selection across all stored predictions, restricted to Q scores of at least 70, decimal odds from 2.00 to below 3.00, and captured bookmaker quotes no older than three hours at decision time. A market qualifies only when its historical hit rate is strictly above 50% and ROI is strictly above 30%. Today's candidates use the same Q and odds bounds, a quote no older than three hours at refresh, and valid pre-kickoff bookmaker provenance for a qualifying market.",
        "research_only": True,
    }
