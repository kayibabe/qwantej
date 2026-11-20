import { describe, expect, it } from 'vitest'
import { SHELL_NAV, bottomNavItems, visibleNavItems } from './shellNav'

const ids = (items: { id: string }[]) => items.map(item => item.id)

describe('shell navigation', () => {
  it('keeps Track in the flat list for every signed-in reader', () => {
    const track = SHELL_NAV.find(item => item.id === 'tracker')
    expect(track).toBeDefined()
    expect(track?.adminOnly).toBeUndefined()
    expect(ids(visibleNavItems(false))).toContain('tracker')
    expect(ids(visibleNavItems(true))).toContain('tracker')
  })

  it('keeps Stats & trends visible for Free even though its page is Pro-gated', () => {
    const insights = SHELL_NAV.find(item => item.id === 'insights')
    expect(insights).toBeDefined()
    expect(insights?.adminOnly).toBeUndefined()
    expect(ids(visibleNavItems(false))).toContain('insights')
    expect(ids(visibleNavItems(true))).toContain('insights')
  })

  it('hides admin-only sections from non-admins', () => {
    expect(ids(visibleNavItems(false))).not.toContain('research')
    expect(ids(visibleNavItems(false))).not.toContain('analytics')
    expect(ids(visibleNavItems(false))).not.toContain('admin')
    expect(ids(visibleNavItems(true))).toEqual(ids(SHELL_NAV))
  })

  it('renders every visible link as a standalone item without section headings', () => {
    expect(ids(visibleNavItems(false))).toEqual(['tickets', 'live', 'insights', 'tracker'])
    expect(visibleNavItems(false).map(item => item.label)).toEqual(['Today', 'Live', 'Stats & trends', 'Track'])
    expect(visibleNavItems(false).map(item => item.label)).not.toContain('Decide')
    expect(visibleNavItems(false).map(item => item.label)).not.toContain('Research')
    expect(ids(visibleNavItems(true))).toEqual(ids(SHELL_NAV))
    expect(visibleNavItems(true).map(item => item.label)).not.toContain('Decide')
    expect(visibleNavItems(true).map(item => item.label)).not.toContain('System')
  })

  it('keeps the public bottom links and swaps in the active section', () => {
    expect(ids(bottomNavItems(false, 'tickets'))).toEqual(['tickets', 'live', 'insights'])
    expect(ids(bottomNavItems(false, 'tracker'))).toEqual(['tickets', 'live', 'tracker'])
    expect(ids(bottomNavItems(true, 'tickets'))).toEqual(['tickets', 'research', 'tracker'])
    expect(ids(bottomNavItems(true, 'admin'))).toEqual(['tickets', 'research', 'admin'])
  })
})
