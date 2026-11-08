from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from app.services.paper_rules import (
    RULES,
    _base_reasons,
    _predicate_reasons,
    build_report,
    list_summaries,
)
from app.services.sweet_spot import digest

NOW = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)


def opportunity(rule_key, **changes):
    base = dict(
        prediction_id=1, kickoff_at=NOW + timedelta(hours=2), created_at=NOW - timedelta(minutes=2),
        decision_at=NOW - timedelta(minutes=1), source_odds_at=NOW - timedelta(hours=1),
        as_of_at=None, feature_snapshot={'original': True}, model_version='v1',
        source_odds_provenance={'bookmaker': 'test', 'source_type': 'test', 'is_fallback': False},
        match_status='SCHEDULED', excluded_from_models=False,
        market='over_4.5', selection='over 4.5', q_score=70, odds=2.4,
        model_probability=0.87, model_edge=0.10,
    )
    base.update(changes)
    return base


def test_protocols_are_json_frozen():
    for key, rule in RULES.items():
        assert rule['mode'] == 'paper_only'
        assert rule['stake_units'] == 1
        datetime.fromisoformat(rule['earliest_kickoff_date'])
        datetime.fromisoformat(rule['minimum_review_date'])
        if 'market' in rule:
            assert rule['q_min'] >= 65
            assert rule['odds_min_inclusive'] < rule['odds_max_exclusive']
        else:
            # JSON round-trip safety: bands must be lists, not tuples.
            assert isinstance(rule['model_band'], list)
            assert isinstance(rule['market_band'], list)
            assert rule['model_band'][0] < rule['model_band'][1]
            assert rule['market_band'][0] < rule['market_band'][1]


def test_market_rule_predicates():
    rule = 'over45-q70-odds200-300-v1'
    assert _predicate_reasons(rule, opportunity(rule)) == []
    assert 'q_below_70_or_invalid' in _predicate_reasons(rule, opportunity(rule, q_score=69.9))
    assert 'q_below_70_or_invalid' in _predicate_reasons(rule, opportunity(rule, q_score=None))
    assert 'odds_outside_range' in _predicate_reasons(rule, opportunity(rule, odds=3.0))
    assert 'odds_outside_range' in _predicate_reasons(rule, opportunity(rule, odds=1.99))
    assert _predicate_reasons(rule, opportunity(rule, odds=2.0)) == []
    assert 'odds_outside_range' in _predicate_reasons(rule, opportunity(rule, odds=float('nan')))


def test_mix_rule_predicates():
    rule = 'mix-q8590-mkt6570-v1'
    # model 0.87, odds 2.0 -> implied 0.5 -> outside [0.65, 0.70)
    assert 'market_implied_outside_band' in _predicate_reasons(rule, opportunity(rule, odds=2.0))
    # odds 1.49 -> implied ~0.671 -> in band
    assert _predicate_reasons(rule, opportunity(rule, odds=1.49)) == []
    assert 'model_probability_outside_band' in _predicate_reasons(rule, opportunity(rule, model_probability=0.84, odds=1.49))
    assert 'model_probability_outside_band' in _predicate_reasons(rule, opportunity(rule, model_probability=0.90, odds=1.49))
    rule2 = 'mix-q7075-mktlt50-v1'
    # odds 2.1 -> implied ~0.476 < 0.50 -> in band; model 0.72 in band
    assert _predicate_reasons(rule2, opportunity(rule2, model_probability=0.72, odds=2.1)) == []
    assert 'market_implied_outside_band' in _predicate_reasons(rule2, opportunity(rule2, model_probability=0.72, odds=1.9))
    assert 'odds_outside_range' not in _predicate_reasons(rule2, opportunity(rule2, model_probability=0.72, odds=2.1))


def test_base_reasons_still_apply_to_rules():
    rule = 'over45-q70-odds200-300-v1'
    assert _base_reasons(opportunity(rule, kickoff_at=NOW), NOW) == ['missed_pre_kickoff_capture']
    assert _base_reasons(opportunity(rule, source_odds_provenance={'bookmaker': 'test', 'source_type': 'test', 'is_fallback': True}), NOW) == ['fallback_odds']
    assert _base_reasons(opportunity(rule), NOW) == []


def event(kind, payload):
    return SimpleNamespace(kind=kind, payload=payload, sha256=digest(payload), event_key=payload.get('event_key', f'{kind}:{digest(payload)[:8]}'))


def decision(rule, match_id, result_day, **changes):
    payload = dict(rule=rule, match_id=match_id, qualified=True, reasons=[],
                   day=result_day, kickoff_at=NOW.isoformat(), odds=2.0,
                   market='over_4.5', selection='over 4.5', competition='L', model_version='v1')
    payload.update(changes)
    return event('decision', payload)


def test_report_review_gate_and_integrity():
    rule = 'over45-q70-odds200-300-v1'
    events = [event('protocol', {**RULES[rule], 'rule': rule, 'activated_at': NOW.isoformat()}),
              decision(rule, 1, '2026-11-09'),
              event('settlement', dict(rule=rule, match_id=1, result='won', profit=1.4)),
              event('settlement', dict(rule=rule, match_id=1, result='lost', profit=-1))]
    report = build_report(events, NOW, rule)
    assert report['summary']['settled'] == 1
    assert report['summary']['profit'] == -1
    assert report['promotion_ready'] is False
    assert report['review_due'] is False
    assert report['mode'] == 'paper_only'
    events[-1].payload['result'] = 'won'
    with pytest.raises(ValueError, match='integrity'):
        build_report(events, NOW, rule)


def test_report_ignores_other_rules_events():
    rule_a, rule_b = 'over45-q70-odds200-300-v1', 'over25-q70-odds200-300-v1'
    events = [decision(rule_a, 1, '2026-11-09'),
              decision(rule_b, 2, '2026-11-09'),
              event('settlement', dict(rule=rule_b, match_id=2, result='won', profit=1.2))]
    report = build_report(events, NOW, rule_a)
    assert report['summary']['picks'] == 1
    assert report['summary']['settled'] == 0


@pytest.mark.asyncio
async def test_list_summaries_shape():
    summaries = await list_summaries_empty()
    assert {s['rule'] for s in summaries} == set(RULES)
    assert all(s['mode'] == 'paper_only' for s in summaries)


async def list_summaries_empty():
    class EmptyDb:
        async def execute(self, *a, **k):
            class Result:
                def scalars(self):
                    return self
                def all(self):
                    return []
            return Result()
    return await list_summaries(EmptyDb())
