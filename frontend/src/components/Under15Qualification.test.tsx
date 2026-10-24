import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import Under15Qualification, { under15Illustration } from './Under15Qualification'

describe('Under 1.5 calculator and evidence', () => {
  it('computes the supplied example and partitions its winning scorelines', () => {
    const result = under15Illustration('.5', '.5', '1.65')!
    expect(result.probability).toBeCloseTo(.7357589)
    expect(result.grade).toBe('A')
    expect(result.ev).toBeCloseTo(.2140022)
    expect(result.zero + result.homeOnly + result.awayOnly).toBeCloseTo(result.probability)
    expect(result.homeOnly + result.awayOnly).toBeCloseTo(result.exactlyOne)
    expect(result.probability + result.twoPlus).toBeCloseTo(1)
    expect(under15Illustration('.6', '.6', '1.65')?.grade).toBe('B')
  })
  it('keeps invalid inputs and illustrative output separate from qualification', () => {
    expect(under15Illustration('', '.5', '1.65')).toBeNull()
    expect(under15Illustration('-1', '.5', '1.65')).toBeNull()
    expect(under15Illustration('Infinity', '.5', '1.65')).toBeNull()
    expect(under15Illustration('.5', '.5', '1')?.ev).toBeNull()
    expect(under15Illustration('.5', '.5', '1.25')!.ev).toBeLessThan(0)
    const html = renderToStaticMarkup(<Under15Qualification />)
    expect(html).toContain('cannot qualify under the new policy')
    expect(html).toContain('1–1, 2–0, 0–2')
    expect(html).toContain('limits are advisory')
    expect(html).toContain('Inputs do not change the selection')
  })
})
