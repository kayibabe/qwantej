import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../auth'
import { addMatchFavorite, fetchMatchFavoriteIds, removeMatchFavorite } from '../../lib/api'

const STORAGE_KEY = 'qwantej.match-favorites.v2'

type FavoriteListener = (ids: number[], error: string | null, remoteReady: boolean) => void

interface FavoriteOperation {
  id: number
  matchId: number
}

interface FavoriteStore {
  /** Last known server (or local, before sign-in) list, without pending toggles. */
  baseline: number[]
  /** Visually applied list: baseline plus queued toggles. */
  ids: number[]
  remoteLoaded: boolean
  readInFlight: Promise<void> | null
  operations: FavoriteOperation[]
  writeQueue: Promise<void>
  listeners: Set<FavoriteListener>
  error: string | null
}

// Tab switches remount the fixture and picks views; favourites are per-account
// state, so share one remote read and one ordered write queue per key.
const stores = new Map<string, FavoriteStore>()
let nextOperationId = 0

function getStore(key: string, initial: number[]): FavoriteStore {
  const existing = stores.get(key)
  if (existing) return existing
  const store: FavoriteStore = {
    baseline: [...initial],
    ids: [...initial],
    remoteLoaded: false,
    readInFlight: null,
    operations: [],
    writeQueue: Promise.resolve(),
    listeners: new Set(),
    error: null,
  }
  stores.set(key, store)
  return store
}

function applyOperations(baseline: number[], operations: FavoriteOperation[]): number[] {
  const ids = new Set(baseline)
  for (const operation of operations) {
    if (ids.has(operation.matchId)) ids.delete(operation.matchId)
    else ids.add(operation.matchId)
  }
  return [...ids]
}

function notify(store: FavoriteStore) {
  for (const listener of store.listeners) listener([...store.ids], store.error, store.remoteLoaded)
}

function recompute(store: FavoriteStore) {
  store.ids = applyOperations(store.baseline, store.operations)
  notify(store)
}

function errorMessage(cause: unknown) {
  return cause instanceof Error ? cause.message : 'Unable to sync match favourites'
}

function ensureRemoteRead(store: FavoriteStore) {
  if (store.remoteLoaded || store.readInFlight) return
  const request = fetchMatchFavoriteIds()
    .then((ids) => {
      store.baseline = ids
      store.remoteLoaded = true
      store.error = null
    })
    .catch((cause: unknown) => {
      // Keep the locally stored list as the working baseline; a later toggle
      // can still attempt the write and will surface a failure if it occurs.
      store.remoteLoaded = true
      store.error = errorMessage(cause)
    })
    .finally(() => {
      store.readInFlight = null
      recompute(store)
    })
  store.readInFlight = request
}

function queueToggle(store: FavoriteStore, matchId: number) {
  const operation: FavoriteOperation = { id: ++nextOperationId, matchId }
  store.operations.push(operation)
  // Optimistic update before the first remote call resolves.
  recompute(store)

  store.writeQueue = store.writeQueue.then(async () => {
    // Decide from the final desired membership, not from the captured click.
    // Rapid toggles that cancel each other out then issue no duplicate writes.
    const desired = store.ids.includes(matchId)
    const alreadyOnServer = store.baseline.includes(matchId)
    if (desired !== alreadyOnServer) {
      try {
        const ids = desired ? await addMatchFavorite(matchId) : await removeMatchFavorite(matchId)
        store.baseline = ids
        store.error = null
      } catch (cause: unknown) {
        // Restore the last confirmed server list (still applying later queued
        // toggles) instead of leaving a failed write visible as saved.
        store.error = errorMessage(cause)
      }
    }
    const index = store.operations.findIndex((candidate) => candidate.id === operation.id)
    if (index !== -1) store.operations.splice(index, 1)
    recompute(store)
  })
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
  const [remoteError, setRemoteError] = useState<string | null>(null)
  const [remoteReady, setRemoteReady] = useState(false)
  const storageKey = `${STORAGE_KEY}:${user ? `user-${user.id}` : 'guest'}`

  useEffect(() => {
    if (authLoading) return
    const store = getStore(storageKey, readStoredFavorites(storageKey))
    const listener: FavoriteListener = (ids, error, ready) => {
      setFavorites(ids)
      setRemoteError(error)
      setRemoteReady(ready)
    }
    store.listeners.add(listener)
    listener([...store.ids], store.error, store.remoteLoaded)
    if (user) ensureRemoteRead(store)
    return () => { store.listeners.delete(listener) }
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
    const store = getStore(storageKey, readStoredFavorites(storageKey))
    if (!user) {
      store.baseline = store.ids.includes(matchId)
        ? store.ids.filter((id) => id !== matchId)
        : [...store.ids, matchId]
      recompute(store)
      return
    }
    queueToggle(store, matchId)
  }, [storageKey, user])

  return { favorites, favoriteIds, toggleFavorite, remoteReady, error: remoteError }
}
