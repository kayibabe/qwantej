import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import Under05Qualification, { under05Illustration } from './Under05Qualification'
import { passesUnder05Value } from '../pages/dailyTickets/helpers'
import type { SelectionSummary } from '../lib/api'

describe('Under 0.5 calculator and safeguards', () => {
  it('computes the supplied example with loss risk, edge and stressed EV', () => {
    const result = under05Illustration('.5', '.5', '3.5')!
    expect(result.probability).toBeCloseTo(.3678794)
    expect(result.grade).toBe('A')
    expect(result.ev).toBeCloseTo(.287578)
    expect(result.implied).toBeCloseTo(.2857143)
    expect(result.edge).toBeCloseTo(.0821652)
    expect(result.stressedEv).toBeCloseTo(.112578)
    expect(result.probability + result.onePlus).toBeCloseTo(1)
  })
  it('does not reuse positive stressed value when the displayed price falls', () => {
    const row = { market: 'under_0.5', best_odds: 3.5,
      under05_qualification: { status: 'QUALIFY', stressed_probability: .3 } } as SelectionSummary
    expect(passesUnder05Value(row)).toBe(true)
    expect(passesUnder05Value({ ...row, best_odds: 3.2 })).toBe(false)
    expect(passesUnder05Value({ ...row, best_odds: null })).toBe(false)
  })
  it('rejects invalid inputs and keeps illustrations separate from qualification', () => {
    expect(under05Illustration('', '.5', '3.5')).toBeNull()
    expect(under05Illustration('-1', '.5', '3.5')).toBeNull()
    expect(under05Illustration('Infinity', '.5', '3.5')).toBeNull()
    expect(under05Illustration('.5', '.5', '1')?.ev).toBeNull()
    const html = renderToStaticMarkup(<Under05Qualification />)
    expect(html).toContain('Only 0–0 wins')
    expect(html).toContain('cannot qualify under the new policy')
    expect(html).toContain('60% loss probability')
    expect(html).toContain('not a validated uncertainty bound')
  })
})
