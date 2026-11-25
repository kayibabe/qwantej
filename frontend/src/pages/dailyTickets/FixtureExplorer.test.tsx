// @vitest-environment jsdom
import { act, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../auth'
import type { MatchFixture } from '../../lib/api'
import { FixtureExplorer, fixturePickLabel, fixtureScore, fixtureStatusLabel } from './FixtureExplorer'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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

const render = (fixtures: MatchFixture[], props: { pickCounts?: Record<number, number> | null; countsStale?: boolean; onOpenPicks?: (matchId: number) => void } = {}) => renderToStaticMarkup(
  <AuthProvider><FixtureExplorer fixtures={fixtures} {...props} /></AuthProvider>,
)

let container: HTMLDivElement | undefined
beforeEach(() => {
  // The provider and the favourites hook both read the session on mount. The
  // badge tests only care about the row, so keep those requests pending.
  vi.stubGlobal('fetch', () => new Promise(() => {}))
})
afterEach(() => {
  container?.remove()
  container = undefined
  vi.unstubAllGlobals()
})

function mount(ui: ReactElement) {
  container = document.createElement('div')
  document.body.appendChild(container)
  act(() => createRoot(container!).render(<AuthProvider>{ui}</AuthProvider>))
  return container
}

describe('fixture result column', () => {
  it('formats a finished score and keeps a zero-zero draw distinct from a missing result', () => {
    expect(fixtureScore(fixture())).toBe('2–1')
    expect(fixtureScore(fixture({ home_goals: 0, away_goals: 0 }))).toBe('0–0')
    expect(fixtureScore(fixture({ home_goals: null, away_goals: null }))).toBeNull()
    expect(fixtureScore(fixture({ home_goals: 1, away_goals: null }))).toBeNull()
  })

  it('shows the score in every row of the list', () => {
    const html = render([fixture(), fixture({ match_id: 2, status: 'scheduled', home_goals: null, away_goals: null })])

    expect(html).toContain('fixture-score')
    expect(html).toContain('2–1')
    expect(html).toContain('Result 2–1')
  })

  it('keeps an empty placeholder so upcoming fixtures stay column-aligned', () => {
    const html = render([fixture({ status: 'scheduled', home_goals: null, away_goals: null })])

    expect(html).toContain('fixture-score')
    expect(html).toContain('empty')
    expect(html).toContain('Result not available')
  })
})

describe('fixture pick count badge', () => {
  it('labels counts in words, singular included', () => {
    expect(fixturePickLabel(1)).toBe('1 pick')
    expect(fixturePickLabel(2)).toBe('2 picks')
    expect(fixturePickLabel(11)).toBe('11 picks')
  })

  it('renders a muted dash when the count is known to be zero', () => {
    const html = render([fixture()], { pickCounts: {} })

    expect(html).toContain('fixture-picks')
    expect(html).toContain('empty')
    expect(html).toContain('No Q≥75 system picks')
  })

  it('shows only the count, never a market name', () => {
    const html = render([fixture()], { pickCounts: { 1: 3 }, onOpenPicks: () => {} })

    expect(html).toContain('3 picks')
    expect(html).not.toContain('Double Chance')
    expect(html).not.toContain('Over 2.5')
  })

  it('opens the picks for that fixture without expanding the row', () => {
    const onOpenPicks = vi.fn()
    const rendered = mount(<FixtureExplorer fixtures={[fixture()]} pickCounts={{ 1: 3 }} onOpenPicks={onOpenPicks} />)

    const badge = rendered.querySelector('button.fixture-picks') as HTMLButtonElement
    expect(badge.textContent).toBe('3 picks')
    expect(badge.getAttribute('aria-label')).toContain('Open 3 picks for Millonarios vs Alianza Valledupar')

    act(() => badge.click())

    expect(onOpenPicks).toHaveBeenCalledTimes(1)
    expect(onOpenPicks).toHaveBeenCalledWith(1)
    expect(rendered.querySelector('details.fixture-row')?.hasAttribute('open')).toBe(false)
  })

  it('keeps the count read-only for accounts that cannot open picks', () => {
    const rendered = mount(<FixtureExplorer fixtures={[fixture()]} pickCounts={{ 1: 3 }} />)

    expect(rendered.querySelector('button.fixture-picks')).toBeNull()
    const badge = rendered.querySelector('span.fixture-picks') as HTMLSpanElement
    expect(badge.textContent).toBe('3 picks')
    expect(badge.title).toContain('open with Pro')
  })

  it('does not claim zero picks when the count request has not succeeded', () => {
    const html = render([fixture()], { pickCounts: null })

    expect(html).toContain('Pick counts unavailable for this refresh')
    expect(html).toContain('Pick count unavailable')
    expect(html).not.toContain('No Q≥75 system picks')
  })

  it('labels stale counts without presenting them as fresh', () => {
    const html = render([fixture()], { pickCounts: { 1: 3 }, countsStale: true })

    expect(html).toContain('Pick counts may be stale; refreshing')
    expect(html).toContain('3 picks')
  })
})

describe('fixture status scope', () => {
  it('offers review states as filterable statuses', () => {
    expect(fixtureStatusLabel('abandoned')).toBe('Abandoned · review')
    expect(fixtureStatusLabel('awarded')).toBe('Awarded · review')

    const html = render([
      fixture(),
      fixture({ match_id: 2, status: 'abandoned', home_team: 'Junior' }),
    ])

    expect(html).toContain('Abandoned · review')
    expect(html).toMatch(/Abandoned · review <b[^>]*>1<\/b>/)
  })

  it('counts status chips from the same scope as the visible rows', () => {
    const rendered = mount(<FixtureExplorer fixtures={[
      fixture(),
      fixture({ match_id: 2, status: 'scheduled', home_team: 'Atletico Nacional', away_team: 'Once Caldas', home_goals: null, away_goals: null }),
    ]} pickCounts={{}} />)

    const search = rendered.querySelector<HTMLInputElement>('input[type="search"]')!
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      setter.call(search, 'Atletico')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })

    expect(rendered.textContent).toContain('Active filters (1)')
    expect(rendered.textContent).toContain('Upcoming 1')
    expect(rendered.textContent).not.toContain('Finished 1')
  })
})
