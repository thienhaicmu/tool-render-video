/**
 * useSystemResources — refcounted shared poller for /api/system/resources.
 * Same pattern as jobsStore.useActiveJobs so multiple subscribers don't
 * fan out duplicate GETs.
 *
 * The hook returns the latest snapshot + status (loading / error).
 * Components are expected to render nullable fields defensively — e.g.
 * a "GPU off" dot when gpu_percent is null.
 */
import { create } from 'zustand'
import { useEffect } from 'react'
import { getSystemResources, type ResourceSnapshot } from '../api/system'
import { isTabHidden } from './pollVisibility'

const POLL_MS = 3000

interface SystemStore {
  snapshot: ResourceSnapshot | null
  loading: boolean
  error: string | null
  _refcount: number
  _intervalId: ReturnType<typeof setInterval> | null
  startPolling: () => void
  stopPolling: () => void
}

async function _fetchAndUpdate(set: (partial: Partial<SystemStore>) => void) {
  try {
    const snap = await getSystemResources()
    set({ snapshot: snap, error: null, loading: false })
  } catch (e) {
    set({
      error: e instanceof Error ? e.message : 'Failed to read resources',
      loading: false,
    })
  }
}

export const useSystemStore = create<SystemStore>((set, get) => ({
  snapshot: null,
  loading: false,
  error: null,
  _refcount: 0,
  _intervalId: null,

  startPolling: () => {
    const next = get()._refcount + 1
    set({ _refcount: next })
    if (next === 1 && get()._intervalId === null) {
      set({ loading: true })
      _fetchAndUpdate(set)
      const id = setInterval(() => { if (isTabHidden()) return; _fetchAndUpdate(set) }, POLL_MS)
      set({ _intervalId: id })
    }
  },

  stopPolling: () => {
    const next = Math.max(0, get()._refcount - 1)
    set({ _refcount: next })
    if (next === 0) {
      const id = get()._intervalId
      if (id !== null) clearInterval(id)
      set({ _intervalId: null })
    }
  },
}))

export function useSystemResources() {
  const startPolling = useSystemStore((s) => s.startPolling)
  const stopPolling  = useSystemStore((s) => s.stopPolling)
  const snapshot     = useSystemStore((s) => s.snapshot)
  const loading      = useSystemStore((s) => s.loading)
  const error        = useSystemStore((s) => s.error)

  useEffect(() => {
    startPolling()
    return () => { stopPolling() }
  }, [startPolling, stopPolling])

  return { snapshot, loading, error }
}
