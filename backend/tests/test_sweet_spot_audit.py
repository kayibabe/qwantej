"""Critical accounting and information-timing checks for the offline audit."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).parents[1]/'scripts'/'sweet_spot_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SweetSpotAuditTests(unittest.TestCase):
    def row(self, **changes):
        return dict(dict(id=1, match_id=1, market='away_win', selection='away_win',
            created_at='2026-10-16T10:00:00+00:00', decision_at='2026-10-16T10:00:01+00:00',
            source_odds_at='2026-10-16T09:00:00+00:00', kickoff_at='2026-10-16T12:00:00+00:00',
            odds=2.5, as_of_at=None, source_odds_provenance={'is_fallback':False},
            feature_snapshot={'recorded':True}, status='FINISHED', home_goals=0, away_goals=1), **changes)

    def prepare(self, rows):
        return audit.prepare(rows, audit.dt('2026-10-18T20:44:42+00:00'))

    def test_transaction_start_can_precede_decision(self):
        rows, excluded = self.prepare([self.row()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['profit'], 1.5)
        self.assertFalse(excluded)

    def test_post_decision_quote_and_post_kickoff_capture_are_rejected(self):
        for fields in [dict(source_odds_at='2026-10-16T10:00:02+00:00'),
                       dict(created_at='2026-10-16T12:00:00+00:00'),
                       dict(decision_at='2026-10-16T12:00:00+00:00')]:
            rows, excluded = self.prepare([self.row(**fields)])
            self.assertFalse(rows)
            self.assertEqual(excluded['timing_or_replay'], 1)

    def test_missing_first_quote_is_not_replaced(self):
        rows, excluded = self.prepare([self.row(odds=None), self.row(id=2)])
        self.assertFalse(rows)
        self.assertEqual(dict(excluded), {'missing_or_invalid_odds':1, 'later_repeat':1})

    def test_current_day_and_postponements_are_excluded(self):
        for fields, reason in [(dict(kickoff_at='2026-10-18T00:00:00+00:00'), 'current_or_future_day'),
                               (dict(status='POSTPONED'), 'no_final_result')]:
            rows, excluded = self.prepare([self.row(**fields)])
            self.assertFalse(rows)
            self.assertEqual(excluded[reason], 1)

    def test_settlement_and_accounting(self):
        self.assertEqual(audit.outcome(self.row(market='dnb_away', home_goals=1)), 0)
        self.assertEqual(audit.outcome(self.row(market='under_2.5')), 1)
        self.assertEqual(audit.outcome(self.row(market='home_win')), -1)
        rows, _ = self.prepare([self.row(), self.row(id=2, match_id=2, home_goals=2)])
        result = audit.stats(rows)
        self.assertEqual(result['profit'], .5)
        self.assertEqual(result['roi'], 25)
        self.assertEqual(result['hit'], 50)


if __name__ == '__main__':
    unittest.main()
