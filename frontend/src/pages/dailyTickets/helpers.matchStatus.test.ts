import { describe, expect, it } from 'vitest'
import type { SelectionSummary } from '../../lib/api'
import { matchDisplayState, matchStatusText } from './helpers'

describe('unresolved provider match statuses', () => {
  it.each([
    ['abandoned', 'abandoned', 'Abandoned · review'],
    ['awarded', 'awarded', 'Awarded · review'],
  ])('keeps %s visible as a review state', (status, state, label) => {
    const row = {
      match_status: status,
      home_goals: 1,
      away_goals: 0,
    } as SelectionSummary

    expect(matchDisplayState(row)).toBe(state)
    expect(matchStatusText(row)).toBe(label)
  })
})
