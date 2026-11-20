import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SelectionSummary } from '../../lib/api'
import { AllMatches, encodeBandMixPairs, matchesBandMix, parseBandMixPairs } from './AllMatches'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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
    expect(html).toContain('The Q ≥75 gate is off')
    expect(html).toContain('95-100% × 70-75%')
  })

  it('keeps only matches for the pairs selected in the URL', () => {
    window.history.replaceState({}, '', '/?match_band_mix=p0,p4')
    const html = renderToStaticMarkup(<AllMatches rows={bandMixRows} onSelect={() => {}} />)

    expect(html).toContain('BandMixLow')
    expect(html).toContain('BandMixTop')
    expect(html).not.toContain('BandMixEdge')
    expect(html).not.toContain('BandMixOutside')
    expect(html).toContain('showing matches with <b>any</b> of &lt;50% × 85-90% · 95-100% × 70-75%')
  })
})

describe('band mix pair selection', () => {
  it('toggles each pair independently and ORs the checked ones', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => { root.render(<AllMatches rows={bandMixRows} onSelect={() => {}} />) })
      const caret = container.querySelector<HTMLButtonElement>('[aria-label="Choose band mix pairs"]')!
      await act(async () => { caret.click() })
      const boxes = [...container.querySelectorAll<HTMLInputElement>('.picks-band-mix-option input')]
      expect(boxes).toHaveLength(5)
      expect(boxes.every((box) => !box.checked)).toBe(true)

      await act(async () => { boxes[0].click() })
      expect(container.textContent).toContain('BandMixLow')
      expect(container.textContent).not.toContain('BandMixEdge')
      expect(container.textContent).not.toContain('BandMixTop')

      await act(async () => { boxes[3].click() })
      expect(container.textContent).toContain('BandMixLow')
      expect(container.textContent).toContain('BandMixEdge')
      expect(container.textContent).not.toContain('BandMixTop')

      await act(async () => { boxes[0].click() })
      expect(container.textContent).not.toContain('BandMixLow')
      expect(container.textContent).toContain('BandMixEdge')
    } finally {
      await act(async () => { root.unmount() })
      container.remove()
    }
  })

  it('notifies the page when band mix changes so it can reload without the Q gate', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    const onBandMixChange = vi.fn()
    try {
      await act(async () => { root.render(<AllMatches rows={bandMixRows} onSelect={() => {}} onBandMixChange={onBandMixChange} />) })
      const caret = container.querySelector<HTMLButtonElement>('[aria-label="Choose band mix pairs"]')!
      await act(async () => { caret.click() })
      const boxes = [...container.querySelectorAll<HTMLInputElement>('.picks-band-mix-option input')]
      await act(async () => { boxes[0].click() })
      expect(onBandMixChange).toHaveBeenLastCalledWith([0])
      await act(async () => { boxes[4].click() })
      expect(onBandMixChange).toHaveBeenLastCalledWith([0, 4])
      await act(async () => { boxes[0].click(); boxes[4].click() })
      expect(onBandMixChange).toHaveBeenLastCalledWith([])
    } finally {
      await act(async () => { root.unmount() })
      container.remove()
    }
  })

  it('reads legacy and per-pair URL encodings', () => {
    expect(parseBandMixPairs(null)).toEqual([])
    expect(parseBandMixPairs('1')).toEqual([0, 1, 2, 3, 4])
    expect(parseBandMixPairs('p4,p0,p0,bogus,p9')).toEqual([0, 4])
    expect(encodeBandMixPairs([0, 4])).toBe('p0,p4')
  })

  it('accepts a match for any selected pair and ignores unselected pairs', () => {
    const low = bandMixRows[0][1][0]
    const edge = bandMixRows[1][1][0]
    const top = bandMixRows[2][1][0]

    expect(matchesBandMix(low, [0])).toBe(true)
    expect(matchesBandMix(low, [1])).toBe(false)
    expect(matchesBandMix(edge, [1, 4])).toBe(false)
    expect(matchesBandMix(edge, [3])).toBe(true)
    expect(matchesBandMix(top, [0, 4])).toBe(true)
    expect(matchesBandMix(top, [0])).toBe(false)
    expect(matchesBandMix(top, [])).toBe(false)
  })
})
