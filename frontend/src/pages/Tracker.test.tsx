import { describe, expect, it } from 'vitest'
import { latestTicketCohorts } from '../components/PaperLedger'
import type { TicketHistoryItem } from '../lib/api'
import { groupMatchHistory } from '../lib/trackerGrouping'

const historyRow = (ticketId: number, version: number, targetDate = '2026-08-30'): TicketHistoryItem => ({
  ticket_id: ticketId,
  target_date: targetDate,
  ticket_type: 'balanced',
  name: 'Balanced',
  status: 'settled',
  version,
  leg_count: 4,
  combined_odds: 8,
  adjusted_probability: .4,
  risk_score: 40,
  avg_q_score: 84,
  model_version: '0.2.1',
  published_at: `${targetDate}T08:00:00Z`,
  publication_hash: `${ticketId}`.repeat(64).slice(0, 64),
  relaxed_tier: false,
  internal_only: false,
  result: 'lost',
  stake: 1,
  return_amount: 0,
  profit_loss: -1,
  settled_at: `${targetDate}T20:00:00Z`,
})

describe('Tracker evidence helpers', () => {
  it('keeps only the latest displayed cohort while retaining prior versions for audit', () => {
    const rows = [historyRow(1, 1), historyRow(2, 2), historyRow(3, 1, '2026-08-29')]
    const latest = latestTicketCohorts(rows)
    expect(latest).toHaveLength(2)
    expect(latest.find(row => row.target_date === '2026-08-30')?.version).toBe(2)
  })

  it('groups match history by newest year, month and date without repeated headings', () => {
    const row = (id: number, date: string) => ({ match_id: id, target_date: date, kickoff_at: `${date}T12:00:00Z`, home_team: 'A', away_team: 'B', competition: 'League', status: 'finished', live_phase: null, elapsed_minutes: null, home_goals: 1, away_goals: 0, outcome: 'won', ticket_types: ['safe'], selections: ['home_win'], selection_evidence: [] })
    const groups = groupMatchHistory([row(1, '2025-12-31'), row(2, '2026-08-29'), row(3, '2026-09-01'), row(4, '2026-08-30')])
    expect(groups.map(group => group.year)).toEqual([2026, 2025])
    expect(groups[0].months.map(month => month.month)).toEqual(['2026-09', '2026-08'])
    expect(groups[0].months[1].matchesByDate.map(date => date.date)).toEqual(['2026-08-30', '2026-08-29'])
  })
})