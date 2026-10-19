from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from app.services.sweet_spot import reasons, metrics, build_report, digest

NOW = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)


def opportunity(**changes):
    return dict(dict(prediction_id=1, kickoff_at=NOW+timedelta(hours=2), created_at=NOW-timedelta(minutes=2),
        decision_at=NOW-timedelta(minutes=1), source_odds_at=NOW-timedelta(hours=1),
        as_of_at=None, feature_snapshot={'original':True}, model_version='v1',
        source_odds_provenance={'bookmaker':'test','source_type':'test','is_fallback':False},
        q_score=65, odds=1.8, match_status='SCHEDULED', excluded_from_models=False), **changes)


@pytest.mark.parametrize('changes,reason', [
    ({'odds':3}, 'odds_outside_range'), ({'q_score':64.99}, 'q_below_65_or_invalid'),
    ({'odds':float('nan')}, 'odds_outside_range'),
    ({'kickoff_at':NOW}, 'missed_pre_kickoff_capture'),
    ({'decision_at':None}, 'missing_timestamps'),
    ({'source_odds_at':NOW+timedelta(seconds=1)}, 'invalid_timestamp_order'),
    ({'source_odds_at':NOW-timedelta(hours=3,seconds=1)}, 'stale_quote_at_capture'),
    ({'as_of_at':NOW}, 'replay'), ({'feature_snapshot':{}}, 'missing_model_context'),
    ({'source_odds_provenance':{'is_fallback':True}}, 'fallback_odds'),
    ({'match_status':'LIVE'}, 'fixture_not_scheduled'),
])
def test_ineligible_evidence(changes, reason):
    assert reason in reasons(opportunity(**changes), NOW)


def test_boundaries_and_outcome_blindness():
    assert reasons(opportunity(), NOW)==[]
    assert reasons(opportunity(source_odds_at=NOW-timedelta(hours=3)), NOW)==[]
    assert reasons(opportunity(home_goals=99, away_goals=0), NOW)==[]


def event(kind,payload):
    return SimpleNamespace(kind=kind,payload=payload,sha256=digest(payload))


def test_corrections_pending_and_review_gate():
    p=dict(match_id=1,qualified=True,reasons=[],day='2026-10-20',kickoff_at=NOW.isoformat(),competition='L',model_version='v1')
    events=[event('decision',p), event('settlement',dict(match_id=1,result='won',profit=1.5)),
            event('settlement',dict(match_id=1,result='lost',profit=-1))]
    report=build_report(events,NOW)
    assert report['summary']['profit']==-1
    assert report['summary']['settled']==1
    assert report['summary']['drawdown']==1
    assert report['review_due'] is False
    assert report['promotion_ready'] is False
    assert report['roi_interval_95'] is None
    events.append(event('settlement',dict(match_id=1,result='pending',profit=None)))
    assert build_report(events,NOW)['summary']['settled']==0


def test_tamper_and_collection_health():
    e=event('run',dict(at=(NOW-timedelta(minutes=16)).isoformat(),day='2026-10-20'))
    assert build_report([e],NOW)['collection_status']=='stale'
    e.payload['at']=NOW.isoformat()
    with pytest.raises(ValueError,match='integrity'):
        build_report([e],NOW)
