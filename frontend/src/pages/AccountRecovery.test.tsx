import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import AccountRecoveryPage from './AccountRecovery'

describe('account recovery surfaces', () => {
  it('offers a reset request form without a token', () => {
    const html = renderToStaticMarkup(<AccountRecoveryPage mode="reset" />)
    expect(html).toContain('Reset your password')
    expect(html).toContain('Send reset link')
    expect(html).toContain('type="email"')
  })

  it('explains where to find the verification link without a token', () => {
    const html = renderToStaticMarkup(<AccountRecoveryPage mode="verify" />)
    expect(html).toContain('Verify your email')
    expect(html).toContain('Open the verification link from your email')
  })
})
