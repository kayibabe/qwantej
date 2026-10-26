"""Immutable Strongest snapshots and the deduplicated recommendation ledger."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AccumulatorTicket,
    Match,
    MatchStatus,
    ModelRun,
    Prediction,
    RunStatus,
    SelectionResult,
    StrongestSelectionSnapshot,
    TicketSelection,
    TicketStatus,
    TicketType,
)
from app.config import CAT
from app.services.settlement import evaluate_selection


def _cat_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    when = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return when.astimezone(CAT).date()


STRONGEST_LIMIT = 8
STRONGEST_MIN_QSCORE = 85.0


async def capture_strongest_snapshots(
    db: AsyncSession,
    model_run_id: int,
    *,
    limit: int = STRONGEST_LIMIT,
    min_qscore: float = STRONGEST_MIN_QSCORE,
    capture_source: str = "model_run_completion",
) -> int:
    """Persist one immutable top-Q-score list for a completed model run."""
    model_run = await db.get(ModelRun, model_run_id)
    if model_run is None:
        raise ValueError(f"Model run {model_run_id} does not exist")
    if model_run.status != RunStatus.COMPLETED:
        raise ValueError(f"Model run {model_run_id} is not completed")

    result = await db.execute(
        select(Prediction)
        .join(Match, Match.id == Prediction.match_id)
        .where(
            Prediction.model_run_id == model_run_id,
            Prediction.q_score >= min_qscore,
            Match.excluded_from_models == False,
        )
        .order_by(Prediction.q_score.desc(), Prediction.id.desc())
        .limit(limit)
    )
    predictions = result.scalars().all()

    existing_result = await db.execute(
        select(StrongestSelectionSnapshot).where(
            StrongestSelectionSnapshot.model_run_id == model_run_id
        )
    )
    existing = {
        snapshot.prediction_id: snapshot
        for snapshot in existing_result.scalars().all()
    }
    for rank, prediction in enumerate(predictions, start=1):
        if prediction.id in existing:
            continue
        db.add(
            StrongestSelectionSnapshot(
                target_date=model_run.target_date,
                model_run_id=model_run.id,
                prediction_id=prediction.id,
                rank=rank,
                capture_source=capture_source,
            )
        )
    await db.flush()
    return len(predictions)


def _canonical_pick_key(target_date: date, prediction: Prediction) -> tuple:
    """Deduplicate repeated tiers/runs while keeping opposite picks distinct."""
    return (
        target_date,
        prediction.match_id,
        prediction.market,
        prediction.selection,
    )


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _new_pick(
    target_date: date,
    prediction: Prediction,
    picked_at: datetime,
    match: Match | None = None,
) -> dict:
    match = match or prediction.match
    return {
        "pick_id": "|".join(
            map(str, _canonical_pick_key(target_date, prediction))
        ),
        "target_date": target_date.isoformat(),
        "match_id": match.id,
        "home_team": match.home_team.name,
        "away_team": match.away_team.name,
        "competition": match.competition.name,
        "kickoff_at": match.kickoff_at.isoformat(),
        "market": prediction.market,
        "selection": prediction.selection,
        "sources": set(),
        "published_tiers": set(),
        "published_ticket_ids": set(),
        "strongest_capture_sources": set(),
        "strongest_rank": None,
        "prediction_ids": {prediction.id},
        "model_run_ids": {prediction.model_run_id} if prediction.model_run_id else set(),
        "model_version": prediction.model_version,
        "model_versions": {prediction.model_version},
        "q_score": prediction.q_score,
        "q_grade": _enum_value(prediction.q_grade),
        "model_probability": prediction.model_probability,
        "edge": prediction.edge,
        "model_spread": prediction.model_agreement,
        "odds": prediction.source_decimal_odds,
        "odds_source": "prediction_snapshot" if prediction.source_decimal_odds else None,
        "source_odds_at": prediction.source_odds_at,
        "first_picked_at": picked_at,
        "selection_settled_at": None,
        "match_status": _enum_value(match.status),
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "result": SelectionResult.PENDING.value,
        "revised_pick": False,
        "revision_count": 1,
        "_published_at": None,
    }


def _authoritative_result(row: dict) -> str:
    if (
        row["match_status"] != MatchStatus.FINISHED.value
        or row["home_goals"] is None
        or row["away_goals"] is None
    ):
        return SelectionResult.PENDING.value
    try:
        return evaluate_selection(
            row["selection"], row["home_goals"], row["away_goals"]
        ).value
    except ValueError:
        try:
            return evaluate_selection(
                row["market"], row["home_goals"], row["away_goals"]
            ).value
        except ValueError:
            return SelectionResult.PENDING.value


def recommendation_metrics(rows: list[dict], stake: float = 1.0) -> dict:
    settled = [row for row in rows if row["result"] != SelectionResult.PENDING.value]
    effective = [
        row
        for row in settled
        if row["result"] in (SelectionResult.WON.value, SelectionResult.LOST.value)
    ]
    priced = [row for row in effective if row.get("odds") and row["odds"] > 1]
    wins = sum(row["result"] == SelectionResult.WON.value for row in effective)
    losses = sum(row["result"] == SelectionResult.LOST.value for row in effective)
    voids = sum(row["result"] == SelectionResult.VOID.value for row in settled)
    staked = len(priced) * stake
    returned = sum(
        stake * row["odds"]
        for row in priced
        if row["result"] == SelectionResult.WON.value
    )
    pnl = returned - staked
    return {
        "unique_picks": len(rows),
        "settled": len(settled),
        "pending": len(rows) - len(settled),
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "settlement_coverage": round(len(settled) / len(rows), 4) if rows else 0.0,
        "hit_rate": round(wins / len(effective), 4) if effective else None,
        "priced_settled": len(priced),
        "missing_odds": len(effective) - len(priced),
        "staked": round(staked, 2),
        "returned": round(returned, 2),
        "profit_loss": round(pnl, 2),
        "roi": round(pnl / staked, 4) if staked else None,
    }


def _source_rows(rows: list[dict], source: str) -> list[dict]:
    if source == "published":
        return [row for row in rows if "published" in row["sources"]]
    if source == "strongest":
        return [row for row in rows if "strongest" in row["sources"]]
    if source == "overlap":
        return [
            row
            for row in rows
            if {"published", "strongest"}.issubset(row["sources"])
        ]
    return rows


def _serialize_pick(row: dict) -> dict:
    item = dict(row)
    item.pop("_published_at", None)
    item["sources"] = sorted(item["sources"])
    item["published_tiers"] = sorted(item["published_tiers"])
    item["published_ticket_ids"] = sorted(item["published_ticket_ids"])
    item["published_ticket_count"] = len(item["published_ticket_ids"])
    item["strongest_capture_sources"] = sorted(item["strongest_capture_sources"])
    item["prediction_ids"] = sorted(item["prediction_ids"])
    item["model_run_ids"] = sorted(item["model_run_ids"])
    item["model_versions"] = sorted(item["model_versions"])
    item["first_picked_at"] = item["first_picked_at"].isoformat()
    if item["source_odds_at"]:
        item["source_odds_at"] = item["source_odds_at"].isoformat()
    if item["selection_settled_at"]:
        item["selection_settled_at"] = item["selection_settled_at"].isoformat()
    return item


async def recommendation_pick_ledger(
    db: AsyncSession,
    *,
    stake: float = 1.0,
    date_from: date | None = None,
    date_to: date | None = None,
    daily_date: date | None = None,
    source: str = "all",
    result_filter: str | None = None,
    market: str | None = None,
    competition: str | None = None,
    model_version: str | None = None,
    limit: int = 1000,
) -> dict:
    """Merge Published and Strongest picks into one deduplicated evidence ledger."""
    rows_by_key: dict[tuple, dict] = {}

    published_result = await db.execute(
        select(AccumulatorTicket)
        .where(
            AccumulatorTicket.ticket_type != TicketType.HIGH_ODDS,
            AccumulatorTicket.status.in_(
                [TicketStatus.PUBLISHED, TicketStatus.SETTLED, TicketStatus.VOID]
            )
        )
        .options(
            selectinload(AccumulatorTicket.selections).selectinload(
                TicketSelection.prediction
            ),
            selectinload(AccumulatorTicket.selections)
            .selectinload(TicketSelection.match)
            .selectinload(Match.home_team),
            selectinload(AccumulatorTicket.selections)
            .selectinload(TicketSelection.match)
            .selectinload(Match.away_team),
            selectinload(AccumulatorTicket.selections)
            .selectinload(TicketSelection.match)
            .selectinload(Match.competition),
        )
        .order_by(AccumulatorTicket.published_at, AccumulatorTicket.id)
    )
    for ticket in published_result.scalars().all():
        for selection in ticket.selections:
            prediction = selection.prediction
            if prediction is None or selection.match is None:
                continue
            # File the pick under the CAT day the match is played. For a
            # same-day ticket that is ticket.target_date; a rolling-horizon
            # leg plays later, and keying it on the ticket date would count
            # it twice alongside that later day's own Strongest snapshot.
            pick_date = _cat_date(selection.match.kickoff_at) or ticket.target_date
            key = _canonical_pick_key(pick_date, prediction)
            row = rows_by_key.setdefault(
                key,
                _new_pick(
                    pick_date,
                    prediction,
                    ticket.published_at,
                    selection.match,
                ),
            )
            row["sources"].add("published")
            row["published_tiers"].add(_enum_value(ticket.ticket_type))
            row["published_ticket_ids"].add(ticket.id)
            row["prediction_ids"].add(prediction.id)
            row["model_versions"].add(prediction.model_version)
            if prediction.model_run_id:
                row["model_run_ids"].add(prediction.model_run_id)
            row["first_picked_at"] = min(row["first_picked_at"], ticket.published_at)
            if row["_published_at"] is None or ticket.published_at < row["_published_at"]:
                row["_published_at"] = ticket.published_at
                row["odds"] = selection.odds_snapshot
                row["odds_source"] = "publication_snapshot"
                row["source_odds_at"] = selection.source_odds_at
                row["q_score"] = selection.q_score_snapshot
                if (ticket.pricing or "model") == "market":
                    # The published snapshot is the fair market price; this
                    # ledger evaluates the model, so keep the model's own view.
                    row["model_probability"] = prediction.model_probability
                    row["edge"] = prediction.edge
                    row["published_fair_probability"] = selection.probability_snapshot
                else:
                    row["model_probability"] = selection.probability_snapshot
                    row["edge"] = selection.edge_snapshot
                row["published_pricing"] = ticket.pricing or "model"
                row["selection_settled_at"] = selection.settled_at

    strongest_result = await db.execute(
        select(StrongestSelectionSnapshot)
        .options(
            selectinload(StrongestSelectionSnapshot.prediction)
            .selectinload(Prediction.match)
            .selectinload(Match.home_team),
            selectinload(StrongestSelectionSnapshot.prediction)
            .selectinload(Prediction.match)
            .selectinload(Match.away_team),
            selectinload(StrongestSelectionSnapshot.prediction)
            .selectinload(Prediction.match)
            .selectinload(Match.competition),
        )
        .order_by(
            StrongestSelectionSnapshot.captured_at,
            StrongestSelectionSnapshot.model_run_id,
            StrongestSelectionSnapshot.rank,
        )
    )
    for snapshot in strongest_result.scalars().all():
        prediction = snapshot.prediction
        if prediction is None or prediction.match is None:
            continue
        key = _canonical_pick_key(snapshot.target_date, prediction)
        row = rows_by_key.setdefault(
            key,
            _new_pick(snapshot.target_date, prediction, snapshot.captured_at),
        )
        row["sources"].add("strongest")
        row["strongest_capture_sources"].add(snapshot.capture_source)
        row["strongest_rank"] = (
            snapshot.rank
            if row["strongest_rank"] is None
            else min(row["strongest_rank"], snapshot.rank)
        )
        row["prediction_ids"].add(prediction.id)
        row["model_versions"].add(prediction.model_version)
        row["model_run_ids"].add(snapshot.model_run_id)
        row["first_picked_at"] = min(row["first_picked_at"], snapshot.captured_at)

    rows = list(rows_by_key.values())
    revisions: dict[tuple, set[str]] = {}
    for row in rows:
        revision_key = (
            row["target_date"],
            row["match_id"],
            row["market"],
        )
        revisions.setdefault(revision_key, set()).add(row["selection"])
    for row in rows:
        revision_key = (
            row["target_date"],
            row["match_id"],
            row["market"],
        )
        row["revision_count"] = len(revisions[revision_key])
        row["revised_pick"] = row["revision_count"] > 1
        row["result"] = _authoritative_result(row)
        if row["result"] == SelectionResult.WON.value and row.get("odds"):
            row["profit_loss"] = round((row["odds"] - 1) * stake, 2)
        elif row["result"] == SelectionResult.LOST.value:
            row["profit_loss"] = -round(stake, 2)
        elif row["result"] == SelectionResult.VOID.value:
            row["profit_loss"] = 0.0
        else:
            row["profit_loss"] = None
        row["reconstructed"] = (
            "strongest" in row["sources"]
            and row["strongest_capture_sources"] == {"historical_backfill"}
        )

    filters = {
        "markets": sorted({row["market"] for row in rows}),
        "competitions": sorted({row["competition"] for row in rows}),
        "model_versions": sorted(
            {version for row in rows for version in row["model_versions"]}
        ),
        "date_min": min((row["target_date"] for row in rows), default=None),
        "date_max": max((row["target_date"] for row in rows), default=None),
    }

    scoped = [
        row
        for row in rows
        if (not date_from or row["target_date"] >= date_from.isoformat())
        and (not date_to or row["target_date"] <= date_to.isoformat())
        and (not market or row["market"] == market)
        and (not competition or row["competition"] == competition)
        and (not model_version or model_version in row["model_versions"])
        and (not result_filter or row["result"] == result_filter)
    ]
    metrics = {
        "all": recommendation_metrics(scoped, stake),
        "published": recommendation_metrics(_source_rows(scoped, "published"), stake),
        "strongest": recommendation_metrics(_source_rows(scoped, "strongest"), stake),
        "overlap": recommendation_metrics(_source_rows(scoped, "overlap"), stake),
    }

    # Compare every observed source × market × model group over
    # the selected date range. Other ledger filters intentionally do not alter
    # this ranking, so changing a filter cannot silently change its baseline.
    date_scoped = [
        row
        for row in rows
        if (not date_from or row["target_date"] >= date_from.isoformat())
        and (not date_to or row["target_date"] <= date_to.isoformat())
    ]
    combination_groups: dict[tuple[str, str, str], list[dict]] = {}
    for source_name in ("all", "published", "strongest", "overlap"):
        source_rows = _source_rows(date_scoped, source_name)
        for row in source_rows:
            versions = row["model_versions"] or {"Unknown model"}
            for version in versions:
                key = (source_name, row["market"], version)
                combination_groups.setdefault(key, []).append(row)
    roi_combinations = []
    for (source_name, market_name, version), group_rows in combination_groups.items():
        roi_combinations.append({
            "source": source_name,
            "market": market_name,
            "model_version": version,
            **recommendation_metrics(group_rows, stake),
        })
    roi_combinations.sort(
        key=lambda item: (
            item["roi"] is not None,
            item["roi"] if item["roi"] is not None else float("-inf"),
            item["priced_settled"],
        ),
        reverse=True,
    )

    displayed = _source_rows(scoped, source)
    displayed.sort(
        key=lambda row: (row["target_date"], row["kickoff_at"], row["q_score"]),
        reverse=True,
    )
    total_rows = len(displayed)
    serialized = [_serialize_pick(row) for row in displayed[:limit]]

    daily_unique = None
    if daily_date is not None:
        selected_date = daily_date.isoformat()
        daily_rows = [row for row in rows if row["target_date"] == selected_date]
        daily_rows.sort(key=lambda row: (row["kickoff_at"], row["q_score"]))
        daily_metrics = recommendation_metrics(daily_rows, stake)
        # Qualify markets from the complete, deduplicated All Unique ledger so
        # each displayed day's picks are gated by system-wide settled evidence.
        market_groups: dict[str, list[dict]] = {}
        for row in rows:
            market_groups.setdefault(row["market"], []).append(row)
        qualifying_markets = []
        qualifying_market_names: set[str] = set()
        for market_name, market_rows in sorted(market_groups.items()):
            market_metrics = recommendation_metrics(market_rows, stake)
            if (
                market_metrics["unique_picks"] >= 5
                and market_metrics["roi"] is not None
                and market_metrics["roi"] >= 0.10
            ):
                qualifying_market_names.add(market_name)
                qualifying_markets.append({
                    "market": market_name,
                    "metrics": market_metrics,
                })
        daily_qualifies = bool(qualifying_market_names)
        # The second daily view reproduces the Published-only simulation using
        # all-time Source × Market × Model combinations at the 5% threshold.
        published_rows = _source_rows(rows, "published")
        published_daily_rows = [
            row for row in published_rows if row["target_date"] == selected_date
        ]
        published_daily_rows.sort(key=lambda row: (row["kickoff_at"], row["q_score"]))
        published_combination_groups: dict[tuple[str, str], list[dict]] = {}
        for row in published_rows:
            for version in row["model_versions"] or {"Unknown model"}:
                published_combination_groups.setdefault(
                    (row["market"], version), []
                ).append(row)
        published_qualifying_combinations = []
        published_qualifying_keys: set[tuple[str, str]] = set()
        for (market_name, version), combination_rows in sorted(
            published_combination_groups.items()
        ):
            combination_metrics = recommendation_metrics(combination_rows, stake)
            if (
                combination_metrics["unique_picks"] >= 5
                and combination_metrics["roi"] is not None
                and combination_metrics["roi"] >= 0.05
            ):
                published_qualifying_keys.add((market_name, version))
                published_qualifying_combinations.append({
                    "market": market_name,
                    "model_version": version,
                    "metrics": combination_metrics,
                })
        published_simulation_rows = [
            _serialize_pick(row)
            for row in published_daily_rows
            if any(
                (row["market"], version) in published_qualifying_keys
                for version in (row["model_versions"] or {"Unknown model"})
            )
        ]
        daily_unique = {
            "date": selected_date,
            "metrics": daily_metrics,
            "qualifies": daily_qualifies,
            "qualifying_markets": qualifying_markets,
            "rows": [
                _serialize_pick(row)
                for row in daily_rows
                if row["market"] in qualifying_market_names
            ],
            "published_simulation": {
                "qualifies": bool(published_qualifying_keys),
                "qualifying_combinations": published_qualifying_combinations,
                "rows": published_simulation_rows,
            },
        }
    return {
        "stake": stake,
        "deduplication_key": [
            "target_date",
            "match_id",
            "market",
            "selection",
        ],
        "total_rows": total_rows,
        "returned_rows": len(serialized),
        "metrics": metrics,
        "roi_combinations": roi_combinations,
        "daily_unique": daily_unique,
        "filters": filters,
        "rows": serialized,
    }
