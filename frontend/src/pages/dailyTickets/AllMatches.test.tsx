import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import type { SelectionSummary } from '../../lib/api'
import { AllMatches } from './AllMatches'

const selection = (overrides: Partial<SelectionSummary> = {}): SelectionSummary => ({
  prediction_id: 1,
  match_id: 1,
  home_team: 'Millonarios',
  away_team: 'Alianza Valledupar',
  competition: 'Colombian Primera A',
  kickoff_at: '2026-11-15T22:30:00+00:00',
  market: 'double_chance_1x',
  selection: 'double_chance_1x',
  model_probability: 0.62,
  q_score: 86,
  edge: 0.04,
  best_odds: 1.82,
  ...overrides,
})

const rows: [number, SelectionSummary[]][] = [
  [1, [selection()]],
  [2, [selection({ prediction_id: 2, match_id: 2, home_team: 'Atletico Nacional', away_team: 'Once Caldas' })]],
]

describe('system picks fixture focus', () => {
  it('narrows the list to the fixture a badge named and shows a clearable chip', () => {
    const html = renderToStaticMarkup(
      <AllMatches rows={rows} onSelect={() => {}} focusMatchId={1} focusLabel="Millonarios vs Alianza Valledupar" onClearFocus={() => {}} />,
    )

    expect(html).toContain('Showing picks for')
    expect(html).toContain('Millonarios vs Alianza Valledupar')
    expect(html).not.toContain('Once Caldas')
    expect(html).toContain('Clear the fixture focus')
  })

  it('shows every fixture when no badge focus is active', () => {
    const html = renderToStaticMarkup(<AllMatches rows={rows} onSelect={() => {}} />)

    expect(html).not.toContain('Showing picks for')
    expect(html).toContain('Millonarios')
    expect(html).toContain('Once Caldas')
  })

  it('says a focused fixture is not loaded yet instead of denying it has picks', () => {
    const html = renderToStaticMarkup(
      <AllMatches
        rows={rows}
        onSelect={() => {}}
        focusMatchId={99}
        focusLabel="Santa Fe vs Junior"
        onClearFocus={() => {}}
      />,
    )

    expect(html).toContain('No loaded picks for Santa Fe vs Junior')
    expect(html).not.toContain('No qualified matches match these filters')
  })
})

afterEach(() => window.history.replaceState({}, '', '/'))

const bandMixRows: [number, SelectionSummary[]][] = [
  [1, [selection({ prediction_id: 11, home_team: 'BandMixLow', model_probability: 0.49, source_implied_probability: 0.87 })]],
  [2, [selection({ prediction_id: 12, home_team: 'BandMixEdge', model_probability: 0.60, source_implied_probability: 0.90, away_team: 'At boundary' })]],
  [3, [selection({ prediction_id: 13, home_team: 'BandMixTop', model_probability: 0.97, source_implied_probability: 0.72 })]],
  [4, [selection({ prediction_id: 14, home_team: 'BandMixOutside', model_probability: 0.62, source_implied_probability: 0.62 })]],
]

describe('one-click band mix filter', () => {
  it('offers the quick button with the count of matching fixtures', () => {
    const html = renderToStaticMarkup(<AllMatches rows={bandMixRows} onSelect={() => {}} />)

    expect(html).toContain('picks-band-mix')
    expect(html).toContain('Band mix')
    expect(html).toContain('>⚡ Band mix <b>3</b>')
  })

  it('keeps only the exact model × market pairs when enabled by URL state', () => {
    window.history.replaceState({}, '', '/?match_band_mix=1')
    const html = renderToStaticMarkup(<AllMatches rows={bandMixRows} onSelect={() => {}} />)

    expect(html).toContain('BandMixLow')
    expect(html).toContain('BandMixEdge')
    expect(html).toContain('BandMixTop')
    expect(html).not.toContain('BandMixOutside')
    expect(html).toContain('Band mix on:')
    expect(html).toContain('95-100% × 70-75%')
  })
})
