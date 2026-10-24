import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import Under25Qualification, { under25Illustration } from './Under25Qualification'

describe('Under 2.5 illustration and evidence', () => {
  it('calculates the supplied 0.9 + 0.8 example without creating a betting signal', () => {
    const result = under25Illustration('0.9', '0.8', '1.55')!
    expect(result.probability).toBeCloseTo(.7572232)
    expect(result.grade).toBe('A')
    expect(result.ev).toBeCloseTo(.173696)
    const html = renderToStaticMarkup(<Under25Qualification />)
    expect(html).toContain('cannot qualify under the new policy')
    expect(html).toContain('do not alter the selection')
    expect(html).toContain('2–1 and 3–0 lose')
  })

  it('rejects missing/invalid inputs and exposes negative value', () => {
    expect(under25Illustration('', '.8', '1.55')).toBeNull()
    expect(under25Illustration('-1', '.8', '1.55')).toBeNull()
    expect(under25Illustration('Infinity', '.8', '1.55')).toBeNull()
    expect(under25Illustration('.9', '.8', '1')?.ev).toBeNull()
    expect(under25Illustration('.9', '.8', '1.18')!.ev).toBeLessThan(0)
  })
})
