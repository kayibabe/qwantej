import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import Under35Qualification, { under35Illustration } from './Under35Qualification'

describe('Under 3.5 illustration and qualification', () => {
  it('keeps 81.9% in Grade B and shows the four-goal tail', () => {
    const result = under35Illustration('1.2', '1.0', '1.35')!
    expect(result.probability).toBeCloseTo(.8193524)
    expect(result.grade).toBe('B')
    expect(result.fourPlus).toBeCloseTo(.1806476)
    expect(result.ev).toBeCloseTo(.1061257)
  })
  it('rejects invalid inputs and does not turn an illustration into a signal', () => {
    expect(under35Illustration('', '1', '1.35')).toBeNull()
    expect(under35Illustration('-1', '1', '1.35')).toBeNull()
    expect(under35Illustration('Infinity', '1', '1.35')).toBeNull()
    expect(under35Illustration('1.2', '1', '1')?.ev).toBeNull()
    expect(under35Illustration('1.2', '1', '1.1')!.ev).toBeLessThan(0)
    const html = renderToStaticMarkup(<Under35Qualification />)
    expect(html).toContain('cannot qualify under the new policy')
    expect(html).toContain('BTTS is optional')
    expect(html).toContain('2–2, 3–1 and 4–0 lose')
    expect(html).toContain('Inputs do not change the selection')
  })
})
