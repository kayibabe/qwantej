export type ModulePage = 'tickets' | 'live' | 'insights' | 'research' | 'tracker' | 'analytics' | 'admin'

export type ShellNavGroup = 'Decide' | 'Research' | 'System'

export interface ShellNavItem {
  id: ModulePage
  label: string
  group: ShellNavGroup
  adminOnly?: boolean
}

/**
 * Flat source of truth for the shell navigation. `adminOnly` is the only
 * visibility gate here, so keep public links ungated even when their page
 * shows a Pro upgrade gate:
 *  - `tracker` stays readable by Free and Pro readers (admin tools are hidden
 *    inside the page, not the link itself).
 *  - `insights` stays visible to Free readers so the gated content is
 *    discoverable instead of looking like a missing section.
 */
export const SHELL_NAV: ShellNavItem[] = [
  { id: 'tickets', label: 'Today', group: 'Decide' },
  { id: 'live', label: 'Live', group: 'Decide' },
  { id: 'insights', label: 'Stats & trends', group: 'Decide' },
  { id: 'research', label: 'Research', group: 'Research', adminOnly: true },
  { id: 'tracker', label: 'Track', group: 'Research' },
  { id: 'analytics', label: 'Validate', group: 'Research', adminOnly: true },
  { id: 'admin', label: 'Admin', group: 'System', adminOnly: true },
]

export const NAV_GROUP_ORDER: ShellNavGroup[] = ['Decide', 'Research', 'System']

export const NAV_META: Record<ModulePage, { icon: string; hint: string }> = {
  tickets: { icon: 'sparkles', hint: 'Today’s fixtures, system picks, and accumulator tickets' },
  live: { icon: 'activity', hint: 'Live scores and match phases' },
  insights: { icon: 'chart', hint: 'League results and team trends' },
  research: { icon: 'flask', hint: 'Research models and selection policies' },
  tracker: { icon: 'list', hint: 'Evidence and personal journal' },
  analytics: { icon: 'chart', hint: 'Performance and model validation' },
  admin: { icon: 'shield', hint: 'System administration' },
}

export function visibleNavItems(isInternal: boolean): ShellNavItem[] {
  return SHELL_NAV.filter(item => !item.adminOnly || isInternal)
}

export function navGroupForPage(page: string): ShellNavGroup | null {
  return SHELL_NAV.find(item => item.id === page)?.group ?? null
}

export function groupedNavItems(isInternal: boolean): Array<{ label: ShellNavGroup; items: ShellNavItem[] }> {
  const visibleNav = visibleNavItems(isInternal)
  return NAV_GROUP_ORDER
    .map(label => ({ label, items: visibleNav.filter(item => item.group === label) }))
    .filter(group => group.items.length > 0)
}

export function bottomNavItems(isInternal: boolean, activePage: string): ShellNavItem[] {
  const visibleNav = visibleNavItems(isInternal)
  const bottomBase: ModulePage[] = isInternal ? ['tickets', 'research', 'tracker'] : ['tickets', 'live', 'insights']
  const activeNavItem = visibleNav.find(item => item.id === activePage)
  const items = bottomBase
    .map(id => visibleNav.find(item => item.id === id))
    .filter((item): item is ShellNavItem => Boolean(item))
    .slice(0, 3)
  if (activeNavItem && !items.some(item => item.id === activeNavItem.id)) {
    items[items.length - 1] = activeNavItem
  }
  return items
}
