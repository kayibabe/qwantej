import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { UngatedDailyPicks, emptyDayCopy } from './Analytics'
import type { DailyUniquePicks, RecommendationPick } from './Analytics'

const pick = (overrides: Partial<RecommendationPick> = {}): RecommendationPick => ({
  pick_id: 'p1',
  target_date: '2026-11-15',
  match_id: 1,
  home_team: 'MVV',
  away_team: 'Vitesse',
  competition: 'Eerste Divisie',
  kickoff_at: '2026-11-15T13:30:00+00:00',
  market: 'double_chance_1x',
  selection: 'double_chance_1x',
  sources: ['published'],
  published_tiers: ['balanced'],
  published_ticket_count: 1,
  strongest_rank: null,
  strongest_capture_sources: [],
  prediction_ids: [1],
  model_run_ids: [1],
  model_version: '0.3.0',
  model_versions: ['0.3.0'],
  q_score: 86,
  q_grade: 'A',
  model_probability: 0.62,
  edge: 0.04,
  model_spread: 0.03,
  odds: 1.82,
  odds_source: 'publication_snapshot',
  source_odds_at: '2026-11-15T04:30:00+00:00',
  first_picked_at: '2026-11-15T04:42:13+00:00',
  selection_settled_at: null,
  match_status: 'scheduled',
  home_goals: null,
  away_goals: null,
  result: 'pending',
  profit_loss: null,
  reconstructed: false,
  revised_pick: false,
  revision_count: 1,
  ...overrides,
})

const emptyGatedDay = (): DailyUniquePicks => ({
  date: '2026-11-15',
  metrics: {
    unique_picks: 1,
    settled: 0,
    pending: 1,
    wins: 0,
    losses: 0,
    voids: 0,
    settlement_coverage: 0,
    hit_rate: null,
    priced_settled: 0,
    missing_odds: 0,
    staked: 0,
    returned: 0,
    profit_loss: 0,
    roi: null,
  },
  qualifies: true,
  qualifying_markets: [],
  rows: [],
  ungated: {
    rows: [pick()],
    market_status: [
      {
        market: 'double_chance_1x',
        status: 'below_threshold',
        unique_picks: 102,
        priced_settled: 96,
        roi: -0.0442,
        recent_picks: 10,
        recent_roi: 0.088,
      },
    ],
  },
  published_simulation: { qualifies: false, qualifying_combinations: [], rows: [] },
})

describe('daily ledger picks panel', () => {
  it('never claims there are no matches when ungated picks exist', () => {
    const copy = emptyDayCopy(10)

    expect(copy.title).toBe('10 picks on this date, none in qualifying markets')
    expect(copy.title).not.toContain('No matches')
    expect(copy.body).toContain('below') // points at the ungated list underneath
  })

  it('keeps the original empty wording when the date genuinely has no picks', () => {
    expect(emptyDayCopy(0).title).toBe('No matches from qualifying markets on this date')
  })

  it('lists ungated picks with their market gate status', () => {
    const html = renderToStaticMarkup(<UngatedDailyPicks daily={emptyGatedDay()} />)

    expect(html).toContain('MVV vs Vitesse')
    expect(html).toContain('Double Chance (1X)')
    expect(html).toContain('1.82')
    expect(html).toContain('Below threshold')
    expect(html).toContain('102 picks')
    expect(html).toContain('-4.4% ROI')
    expect(html).not.toContain('No matches from qualifying markets')
  })

  it('explains a genuinely empty date instead of showing an empty table', () => {
    const day = emptyGatedDay()
    day.ungated = { rows: [], market_status: [] }

    const html = renderToStaticMarkup(<UngatedDailyPicks daily={day} />)

    expect(html).toContain('No system picks for this date')
    expect(html).not.toContain('<table')
  })

  it('renders nothing when the payload predates the ungated field', () => {
    const day = emptyGatedDay()
    delete day.ungated

    expect(renderToStaticMarkup(<UngatedDailyPicks daily={day} />)).toBe('')
  })
})
