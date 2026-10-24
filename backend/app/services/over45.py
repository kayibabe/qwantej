"""Provisional, evidence-first qualification for regulation-time Over 4.5."""

import math
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICY_VERSION = "over45-v1-provisional"
THRESHOLDS = {
    "projected_xg": 4.0,
    "combined_scored": 4.0,
    "over25_frequency": 0.80,
    "over35_frequency": 0.60,
    "over45_frequency": 0.35,
    "combined_shots_on_target": 11.0,
    "combined_big_chances": 5.0,
    "max_team_projected_goals": 2.3,
    "first_half_over15_frequency": 0.55,
    "btts_frequency": 0.70,
}


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def probability_grade(probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in ((.45, "A+"), (.35, "A"), (.25, "B"), (.15, "C"), (0, "D")) if p >= floor)


def qualify_over45(probability, odds, evidence=None):
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, "over_4.5")
    if shared_probability is not None:
        probability = shared_probability
    metrics = evidence.get("metrics") or {}
    checks = []
    reasons = []
    warnings = []
    for key, threshold in THRESHOLDS.items():
        value = number(metrics.get(key))
        if value is not None and (value < 0 or (key.endswith("frequency") and value > 1)):
            value = None
        status = "missing" if value is None else "pass" if value >= threshold else "below"
        required = key == "projected_xg"
        checks.append(dict(key=key, value=value, threshold=threshold, status=status, required=required))
        if required and status != "pass":
            reasons.append(f"OVER45_{key.upper()}_{status.upper()}")
        elif not required and status != "pass":
            warnings.append(f"OVER45_{key.upper()}_{status.upper()}")
    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 8 <= counts[side] <= 12 for side in ("home", "away")):
        reasons.append("OVER45_INSUFFICIENT_RECENT_SAMPLE")
    calibration = evidence.get("calibration") or {}
    market_calibrated = (
        calibration.get("status") == "promoted"
        and calibration.get("profile_id") is not None
        and calibration.get("method") == "platt_logit"
        and bool(calibration.get("checks"))
        and all(value is True for value in calibration["checks"].values())
    )
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append("OVER45_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append("OVER45_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append("OVER45_SHARED_GOALS_FORECAST_UNCALIBRATED")
    # A numerical screen is not evidence of a tactical/lineup review.
    for key in ("opponent_strength", "tactics_lineups"):
        if (evidence.get("context_review") or {}).get(key) != "verified":
            reasons.append(f"OVER45_{key.upper()}_UNVERIFIED")
    grade = probability_grade(probability)
    if grade is None or grade in ("C", "D"):
        reasons.append("OVER45_PROBABILITY_BELOW_THRESHOLD" if grade else "OVER45_PROBABILITY_MISSING")
    price = number(odds)
    ev = probability * price - 1 if grade and price is not None and price > 1 else None
    if ev is None or ev <= 0:
        reasons.append("OVER45_NO_POSITIVE_EXPECTED_VALUE")
    projected = number(metrics.get("projected_xg"))
    shared = shared_forecast or evidence.get("shared_distribution") or {}
    shared_baseline = (shared.get("markets") or {}).get("over_4.5")
    poisson = (shared_baseline if number(shared_baseline) is not None else
               1 - math.exp(-projected) * sum(projected ** k / math.factorial(k) for k in range(5))
               if projected is not None and 0 <= projected <= 100 else None)
    return {
        "policy_version": POLICY_VERSION, "status": "REJECT" if reasons else "QUALIFY",
        "provisional": True, "grade": grade, "probability": probability if grade else None,
        "calibrated": calibrated, "expected_value": ev,
        "fair_odds": 1 / probability if grade and probability > 0 else None,
        "poisson_baseline": poisson, "shared_distribution": shared or None,
        "shared_goals_forecast": shared_forecast,
        "probability_source": "shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
        "checks": checks, "reasons": reasons, "warnings": warnings,
        "sample_sizes": counts, "source": evidence.get("source", "missing"),
    }


def prediction_qualification(prediction):
    if prediction.market != "over_4.5":
        return None
    snapshot = prediction.feature_snapshot or {}
    return qualify_over45(prediction.model_probability, prediction.source_decimal_odds, snapshot.get("over45_evidence"))


async def load_recent_evidence(db, match, cutoff, sample_limit=12):
    """Latest venue fixtures, strictly before the decision and target.

    Defaults to 12; the exact-zero policy requests its own 15-match window.

    xG is a transparent venue-split historical projection, not the target
    match's observed xG. Missing shots/xG/half-time results stay missing.
    """
    from sqlalchemy import select
    from app.models import Match, MatchStatus, TeamStats, Team
    from sqlalchemy.orm import aliased

    samples = {}
    home_team, away_team = aliased(Team), aliased(Team)
    for side, team_id in (("home", match.home_team_id), ("away", match.away_team_id)):
        team_column = Match.home_team_id if side == "home" else Match.away_team_id
        rows = (await db.execute(
            select(Match, TeamStats.shots_on_target, home_team.name, away_team.name)
            .join(home_team, home_team.id == Match.home_team_id)
            .join(away_team, away_team.id == Match.away_team_id)
            .outerjoin(TeamStats, (TeamStats.match_id == Match.id) & (TeamStats.team_id == team_id))
            .where(team_column == team_id, Match.status == MatchStatus.FINISHED,
                   Match.kickoff_at < cutoff, Match.kickoff_at < match.kickoff_at,
                   Match.home_goals.is_not(None), Match.away_goals.is_not(None))
            .order_by(Match.kickoff_at.desc(), Match.id.desc()).limit(sample_limit)
        )).all()
        samples[side] = [dict(
            id=m.id, kickoff_at=m.kickoff_at.isoformat(), home_team=home_name, away_team=away_name,
            home_goals=m.home_goals, away_goals=m.away_goals,
            scored=m.home_goals if side == "home" else m.away_goals,
            conceded=m.away_goals if side == "home" else m.home_goals,
            xg=m.home_xg if side == "home" else m.away_xg,
            xga=m.away_xg if side == "home" else m.home_xg,
            shots=shots, ht=(m.home_goals_ht + m.away_goals_ht)
            if m.home_goals_ht is not None and m.away_goals_ht is not None else None,
        ) for m, shots, home_name, away_name in rows]
    evidence = summarize_samples(samples)
    evidence["cutoff_at"] = cutoff.isoformat()
    return evidence


def summarize_samples(samples):
    def mean(rows, key):
        values = [number(row.get(key)) for row in rows]
        return sum(values) / len(values) if values and all(v is not None and v >= 0 for v in values) else None

    home, away = samples["home"], samples["away"]
    def combined(key):
        values = [mean(rows, key) for rows in (home, away)]
        return sum(values) if all(v is not None for v in values) else None

    metrics = {"combined_scored": combined("scored"), "combined_conceded": combined("conceded"),
               "combined_shots_on_target": combined("shots")}
    xg, xga, ht = combined("xg"), combined("xga"), combined("ht")
    metrics["projected_xg"] = (xg + xga) / 2 if xg is not None and xga is not None else None
    home_xg, home_xga = mean(home, "xg"), mean(home, "xga")
    away_xg, away_xga = mean(away, "xg"), mean(away, "xga")
    metrics["home_projected_goals"] = (home_xg + away_xga) / 2 if home_xg is not None and away_xga is not None else None
    metrics["away_projected_goals"] = (away_xg + home_xga) / 2 if away_xg is not None and home_xga is not None else None
    team_projections = [metrics["home_projected_goals"], metrics["away_projected_goals"]]
    metrics["max_team_projected_goals"] = max(team_projections) if all(v is not None for v in team_projections) else None
    metrics["expected_first_half_goals"] = ht / 2 if ht is not None else None
    metrics["first_half_over05_frequency"] = sum(
        sum(r.get("ht") is not None and r["ht"] >= 1 for r in rows) / len(rows)
        for rows in (home, away)
    ) / 2 if home and away else None
    metrics["first_half_over15_frequency"] = sum(
        sum(r.get("ht") is not None and r["ht"] >= 2 for r in rows) / len(rows)
        for rows in (home, away)
    ) / 2 if home and away else None
    # Equal team weighting; frequencies describe matches, never sum to 200%.
    for key, threshold in ((f"over{n}5_frequency", n + .5) for n in range(5)):
        metrics[key] = sum(sum(r["scored"] + r["conceded"] > threshold for r in rows) / len(rows) for rows in (home, away)) / 2 if home and away else None
        metrics[key.replace("over", "under")] = 1 - metrics[key] if metrics[key] is not None else None
    metrics["btts_frequency"] = sum(sum(r["scored"] > 0 and r["conceded"] > 0 for r in rows) / len(rows) for rows in (home, away)) / 2 if home and away else None
    return {"metrics": metrics, "sample_sizes": {side: len(rows) for side, rows in samples.items()},
            "match_ids": {side: [r["id"] for r in rows] for side, rows in samples.items()},
            "recent_matches": samples,
            "source": "recent_venue_split_history", "context_review": {}}
