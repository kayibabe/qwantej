import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../auth'
import { addMatchFavorite, fetchMatchFavoriteIds, removeMatchFavorite } from '../../lib/api'

const STORAGE_KEY = 'qwantej.match-favorites.v2'

// Tab switches remount the fixture and picks views; favourites are per-account
// state, so share one remote read per session instead of refetching on mount.
const remoteFavorites = new Map<string, number[]>()
const remoteFavoritesInFlight = new Map<string, Promise<number[]>>()

function loadRemoteFavorites(key: string) {
  const cached = remoteFavorites.get(key)
  if (cached) return Promise.resolve(cached)
  const inFlight = remoteFavoritesInFlight.get(key)
  if (inFlight) return inFlight
  const request = fetchMatchFavoriteIds()
    .then(ids => {
      remoteFavorites.set(key, ids)
      return ids
    })
    .finally(() => { remoteFavoritesInFlight.delete(key) })
  remoteFavoritesInFlight.set(key, request)
  return request
}

function readStoredFavorites(key: string): number[] {
  try {
    const saved = localStorage.getItem(key)
    const parsed: unknown = saved ? JSON.parse(saved) : []
    return Array.isArray(parsed)
      ? [...new Set(parsed.filter((id): id is number => Number.isSafeInteger(id) && id > 0))]
      : []
  } catch {
    return []
  }
}

export function useFavoriteMatches() {
  const { user, loading: authLoading } = useAuth()
  const [favorites, setFavorites] = useState<number[]>([])
  const [remoteReady, setRemoteReady] = useState(false)
  const storageKey = `${STORAGE_KEY}:${user ? `user-${user.id}` : 'guest'}`

  useEffect(() => {
    if (authLoading) return
    let active = true
    setRemoteReady(false)
    setFavorites(readStoredFavorites(storageKey))
    if (!user) return () => { active = false }

    const cached = remoteFavorites.get(storageKey)
    if (cached) {
      setFavorites(cached)
      setRemoteReady(true)
      return () => { active = false }
    }

    loadRemoteFavorites(storageKey).then(ids => {
      if (!active) return
      setFavorites(ids)
      setRemoteReady(true)
    }).catch(() => {
      if (active) setRemoteReady(true)
    })
    return () => { active = false }
  }, [authLoading, storageKey, user])

  useEffect(() => {
    if (authLoading) return
    try {
      localStorage.setItem(storageKey, JSON.stringify(favorites))
    } catch {
      // Keep favourites usable for the current view when browser storage is unavailable.
    }
  }, [authLoading, favorites, storageKey])

  const favoriteIds = useMemo(() => new Set(favorites), [favorites])
  const toggleFavorite = useCallback((matchId: number) => {
    const adding = !favoriteIds.has(matchId)
    setFavorites(current => {
      const next = current.includes(matchId)
        ? current.filter(id => id !== matchId)
        : [...current, matchId]
      remoteFavorites.set(storageKey, next)
      return next
    })
    if (!user || !remoteReady) return
    const update = adding ? addMatchFavorite(matchId) : removeMatchFavorite(matchId)
    update.then(ids => {
      remoteFavorites.set(storageKey, ids)
      setFavorites(ids)
    }).catch(() => setRemoteReady(false))
  }, [favoriteIds, remoteReady, storageKey, user])

  return { favorites, favoriteIds, toggleFavorite }
}
