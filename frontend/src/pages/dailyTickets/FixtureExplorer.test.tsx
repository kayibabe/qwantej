import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../../auth'
import type { MatchFixture } from '../../lib/api'
import { FixtureExplorer, fixtureScore } from './FixtureExplorer'

const fixture = (overrides: Partial<MatchFixture> = {}): MatchFixture => ({
  match_id: 1,
  home_team: 'Millonarios',
  away_team: 'Alianza Valledupar',
  competition: 'Colombian Primera A',
  kickoff_at: '2026-11-15T22:30:00+00:00',
  status: 'finished',
  home_goals: 2,
  away_goals: 1,
  ...overrides,
})

const render = (fixtures: MatchFixture[]) => renderToStaticMarkup(
  <AuthProvider><FixtureExplorer fixtures={fixtures} /></AuthProvider>,
)

describe('fixture result column', () => {
  it('formats a finished score and keeps a zero-zero draw distinct from a missing result', () => {
    expect(fixtureScore(fixture())).toBe('2–1')
    expect(fixtureScore(fixture({ home_goals: 0, away_goals: 0 }))).toBe('0–0')
    expect(fixtureScore(fixture({ home_goals: null, away_goals: null }))).toBeNull()
    expect(fixtureScore(fixture({ home_goals: 1, away_goals: null }))).toBeNull()
  })

  it('shows the score in every row of the list', () => {
    const html = render([fixture(), fixture({ match_id: 2, status: 'scheduled', home_goals: null, away_goals: null })])

    expect(html).toContain('class="fixture-score"')
    expect(html).toContain('2–1')
    expect(html).toContain('Result 2–1')
  })

  it('keeps an empty placeholder so upcoming fixtures stay column-aligned', () => {
    const html = render([fixture({ status: 'scheduled', home_goals: null, away_goals: null })])

    expect(html).toContain('class="fixture-score empty"')
    expect(html).toContain('Result not available')
  })
})
