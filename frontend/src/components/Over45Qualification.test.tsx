import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import Over45Qualification from './Over45Qualification'

describe('Over 4.5 evidence', () => {
  it('does not present a legacy selection without evidence as qualified', () => {
    const html = renderToStaticMarkup(<Over45Qualification />)
    expect(html).toContain('It cannot qualify under the new policy')
    expect(html).toContain('BTTS is optional')
    expect(html).toContain('Extra time and penalties do not count')
  })

  it('distinguishes an A+ probability from qualification and calibration', () => {
    const html = renderToStaticMarkup(<Over45Qualification assessment={{
      policy_version: 'over45-v1-provisional', provisional: true, status: 'REJECT',
      grade: 'A+', probability: .45, calibrated: false, expected_value: .35,
      fair_odds: 1 / .45, sample_sizes: { home: 8, away: 12 },
      checks: [{ key: 'projected_xg', value: null, threshold: 3.8, status: 'missing', required: true }],
      reasons: ['OVER45_CALIBRATION_UNVALIDATED'],
    }} />)
    expect(html).toContain('REJECT · Probability grade A+')
    expect(html).toContain('Unvalidated estimate')
    expect(html).toContain('calibration unvalidated')
    expect(html).toContain('Unavailable')
  })
})
