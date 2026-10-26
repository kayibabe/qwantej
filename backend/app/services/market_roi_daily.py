"""Daily market hit-rate and ROI scan using point-in-time prices."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from app.config import CAT, cat_day_bounds_utc, settings
from app.models.competition import Competition
from app.models.match import Match, MatchStatus
from app.models.prediction import Prediction
from app.models.research import SelectionResult
from app.models.team import Team
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
        .options(
            load_only(
                Prediction.id,
                Prediction.match_id,
                Prediction.market,
                Prediction.selection,
                Prediction.q_score,
                Prediction.source_odds_id,
                Prediction.source_odds_at,
                Prediction.source_decimal_odds,
                Prediction.source_odds_provenance,
                Prediction.decision_at,
                Prediction.as_of_at,
                Prediction.created_at,
            ),
            joinedload(Prediction.match).load_only(
                Match.id,
                Match.kickoff_at,
                Match.status,
                Match.home_goals,
                Match.away_goals,
            ),
        )
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
            load_only(
                Prediction.id,
                Prediction.match_id,
                Prediction.market,
                Prediction.selection,
                Prediction.q_score,
                Prediction.source_odds_id,
                Prediction.source_odds_at,
                Prediction.source_decimal_odds,
                Prediction.source_odds_provenance,
                Prediction.decision_at,
                Prediction.as_of_at,
                Prediction.created_at,
                Prediction.model_probability,
                Prediction.q_grade,
                Prediction.recommendation_status,
            ),
            joinedload(Prediction.match)
            .load_only(
                Match.id,
                Match.kickoff_at,
                Match.status,
                Match.home_goals,
                Match.away_goals,
            )
            .joinedload(Match.home_team)
            .load_only(Team.id, Team.name),
            joinedload(Prediction.match)
            .load_only(
                Match.id,
                Match.kickoff_at,
                Match.status,
                Match.home_goals,
                Match.away_goals,
            )
            .joinedload(Match.away_team)
            .load_only(Team.id, Team.name),
            joinedload(Prediction.match)
            .load_only(
                Match.id,
                Match.kickoff_at,
                Match.status,
                Match.home_goals,
                Match.away_goals,
            )
            .joinedload(Match.competition)
            .load_only(Competition.id, Competition.name),
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

    settled_market_performance = await settled_daily_pick_market_performance(db)

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
        "settled_daily_pick_market_performance": settled_market_performance,
        "unsupported_outcomes_excluded": unsupported,
        "method": "Historical hit rate and flat one-unit ROI use the latest valid pre-kickoff prediction per unique fixture-market-selection across all stored predictions, restricted to Q scores of at least 70, decimal odds from 2.00 to below 3.00, and captured bookmaker quotes no older than three hours at decision time. A market qualifies only when its historical hit rate is strictly above 50% and ROI is strictly above 30%. Today's candidates use the same Q and odds bounds, a quote no older than three hours at refresh, and valid pre-kickoff bookmaker provenance for a qualifying market.",
        "research_only": True,
    }


async def settled_daily_pick_market_performance(db: AsyncSession) -> dict:
    """Cumulative settled performance of Daily Match Picks since 2026-10-01.

    Rebuild each CAT day's pick set using only results known before that day,
    matching daily_market_roi's historical market gates. A date is added only
    after every reconstructed pick that day has a terminal match status.
    """
    start_date = date(2026, 10, 1)
    today = datetime.now(CAT).date()
    now = datetime.now(timezone.utc)
    _, range_end = cat_day_bounds_utc(today)
    result = await db.execute(
        select(Prediction)
        .join(Match, Match.id == Prediction.match_id)
        .options(
            load_only(
                Prediction.id, Prediction.match_id, Prediction.market,
                Prediction.selection, Prediction.q_score,
                Prediction.source_odds_id, Prediction.source_odds_at,
                Prediction.source_decimal_odds,
                Prediction.source_odds_provenance, Prediction.decision_at,
                Prediction.as_of_at, Prediction.created_at,
            ),
            joinedload(Prediction.match).load_only(
                Match.id, Match.kickoff_at, Match.status, Match.home_goals,
                Match.away_goals,
            ),
        )
        .where(
            Match.kickoff_at < range_end,
            Prediction.q_score >= MIN_Q_SCORE,
            Prediction.source_odds_id.is_not(None),
            Prediction.source_odds_at.is_not(None),
            Prediction.source_decimal_odds >= MIN_DECIMAL_ODDS,
            Prediction.source_decimal_odds < MAX_DECIMAL_ODDS,
        )
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
    )
    predictions = result.scalars().all()

    # Cache valid rows/outcomes once; the same eligible records feed both the
    # as-of-date qualification history and that day's pick set.
    valid_predictions = [
        prediction for prediction in predictions
        if prediction.match is not None
        and prediction.q_score >= MIN_Q_SCORE
        and prediction.source_decimal_odds is not None
        and MIN_DECIMAL_ODDS <= prediction.source_decimal_odds < MAX_DECIMAL_ODDS
        and _fresh_pre_kickoff_prediction(prediction, now)
        and timedelta(0)
        <= _as_utc(prediction.decision_at or prediction.as_of_at or prediction.created_at)
        - _as_utc(prediction.source_odds_at)
        <= MAX_QUOTE_AGE
    ]

    settled_by_market: dict[str, list[tuple[Prediction, SelectionResult, date]]] = defaultdict(list)
    incomplete_dates: list[str] = []
    included_dates: list[str] = []

    current_date = start_date
    terminal_statuses = {
        MatchStatus.FINISHED, MatchStatus.POSTPONED, MatchStatus.CANCELLED,
        MatchStatus.ABANDONED, MatchStatus.AWARDED,
    }
    while current_date <= today:
        history: dict[tuple[int, str, str], tuple[Prediction, SelectionResult]] = {}
        for prediction in valid_predictions:
            match = prediction.match
            match_date = _as_utc(match.kickoff_at).astimezone(CAT).date()
            if (
                match_date >= current_date
                or match.status != MatchStatus.FINISHED
                or match.home_goals is None
                or match.away_goals is None
            ):
                continue
            key = (prediction.match_id, prediction.market, prediction.selection)
            if key in history:
                continue
            try:
                outcome = evaluate_selection(
                    prediction.selection, match.home_goals, match.away_goals
                )
            except ValueError:
                try:
                    outcome = evaluate_selection(
                        prediction.market, match.home_goals, match.away_goals
                    )
                except ValueError:
                    continue
            if outcome in (SelectionResult.WON, SelectionResult.LOST):
                history[key] = (prediction, outcome)

        history_by_market: dict[str, list[tuple[Prediction, SelectionResult]]] = defaultdict(list)
        for (match_id, market, _selection), item in history.items():
            history_by_market[market].append(item)

        qualifying_markets = set()
        for market, items in history_by_market.items():
            wins = sum(outcome == SelectionResult.WON for _, outcome in items)
            losses = len(items) - wins
            if not wins + losses:
                continue
            roi = sum(
                prediction.source_decimal_odds - 1
                if outcome == SelectionResult.WON else -1
                for prediction, outcome in items
            ) / (wins + losses)
            if wins / (wins + losses) > HIT_RATE_THRESHOLD and roi > ROI_THRESHOLD:
                qualifying_markets.add(market)

        daily_predictions: dict[tuple[int, str, str], Prediction] = {}
        for prediction in valid_predictions:
            match = prediction.match
            match_date = _as_utc(match.kickoff_at).astimezone(CAT).date()
            if (
                match_date != current_date
                or prediction.market not in qualifying_markets
                or match.status not in {
                    MatchStatus.SCHEDULED, MatchStatus.LIVE, MatchStatus.FINISHED,
                    MatchStatus.POSTPONED, MatchStatus.CANCELLED,
                }
            ):
                continue
            key = (prediction.match_id, prediction.market, prediction.selection)
            if key not in daily_predictions:
                daily_predictions[key] = prediction

        if daily_predictions:
            if any(prediction.match.status not in terminal_statuses for prediction in daily_predictions.values()):
                incomplete_dates.append(current_date.isoformat())
            else:
                included_dates.append(current_date.isoformat())
                for prediction in daily_predictions.values():
                    match = prediction.match
                    if match.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
                        continue  # Voided picks return the stake; they do not count in ROI.
                    if (
                        match.status != MatchStatus.FINISHED
                        or match.home_goals is None
                        or match.away_goals is None
                    ):
                        continue
                    try:
                        outcome = evaluate_selection(
                            prediction.selection, match.home_goals, match.away_goals
                        )
                    except ValueError:
                        try:
                            outcome = evaluate_selection(
                                prediction.market, match.home_goals, match.away_goals
                            )
                        except ValueError:
                            continue
                    if outcome in (SelectionResult.WON, SelectionResult.LOST):
                        settled_by_market[prediction.market].append(
                            (prediction, outcome, current_date)
                        )

        current_date += timedelta(days=1)

    rows = []
    for market, items in settled_by_market.items():
        def performance(window_items):
            wins = sum(outcome == SelectionResult.WON for _, outcome, _ in window_items)
            losses = sum(outcome == SelectionResult.LOST for _, outcome, _ in window_items)
            count = wins + losses
            pnl = sum(
                prediction.source_decimal_odds - 1
                if outcome == SelectionResult.WON else -1
                for prediction, outcome, _ in window_items
            )
            return {
                "selections": count,
                "wins": wins,
                "losses": losses,
                "hit_rate": wins / count if count else None,
                "flat_stake_pnl": pnl,
                "roi": pnl / count if count else None,
            }

        earlier_items = [item for item in items if item[2] < date(2026, 10, 20)]
        later_items = [item for item in items if item[2] >= date(2026, 10, 20)]
        all_stats = performance(items)
        rows.append({
            "market": market,
            **all_stats,
            "earlier_roi": performance(earlier_items)["roi"],
            "later_roi": performance(later_items)["roi"],
        })
    rows.sort(key=lambda row: (-(row["roi"] if row["roi"] is not None else float("-inf")), row["market"]))

    return {
        "date_from": start_date.isoformat(),
        "calculated_at": now.isoformat(),
        "completed_through": max(included_dates) if included_dates else None,
        "included_days": included_dates,
        "waiting_for_settlement_days": incomplete_dates,
        "earlier_through": "2026-10-19",
        "later_from": "2026-10-20",
        "markets": rows,
    }
