import { describe, expect, it } from 'vitest'
import {
  formatMarket,
  formatSelection,
  installMarketCatalog,
  selectionRepeatsMarket,
  type MarketCatalogEntry,
} from './api'
import { marketLabel } from '../utils'

const catalog: MarketCatalogEntry[] = [
  {
    legacy_key: 'over_2.5',
    selection_id: 'over',
    family: 'total_goals',
    display_name: 'Over 2.5 goals',
    scored: true,
    qualification_mode: 'market_specific_provisional',
    qualification_policy_id: 'over25-v1-provisional',
  },
  {
    legacy_key: 'home_win',
    selection_id: 'home',
    family: 'match_result',
    display_name: 'Home win',
    scored: true,
    qualification_mode: 'generic_recommendation_only',
    qualification_policy_id: null,
  },
]

describe('market catalogue display integration', () => {
  it('uses canonical display names for legacy market keys and selection keys', () => {
    installMarketCatalog(catalog)

    expect(formatMarket('over_2_5')).toBe('Over 2.5 goals')
    expect(marketLabel('over_2.5')).toBe('Over 2.5 goals')
    expect(formatSelection('home_win')).toBe('Home win')
    expect(formatMarket('btts')).toBe('Both Teams to Score')
  })

  it('suppresses duplicate market labels when selection IDs differ from legacy keys', () => {
    installMarketCatalog(catalog)

    expect(selectionRepeatsMarket('home_win', 'Home')).toBe(true)
    expect(selectionRepeatsMarket('over_2.5', 'Over 2.5')).toBe(true)
    expect(selectionRepeatsMarket('over_2.5', 'Under 2.5')).toBe(false)
  })

  it('keeps the existing humanized fallback for keys absent from the catalogue', () => {
    installMarketCatalog(catalog)

    expect(formatMarket('corner_count')).toBe('Corner Count')
  })
})
