/**
 * jobsStore — shared zustand store for /api/jobs/history polling.
 *
 * Added 2026-06-15 to consolidate three separate polls that all fetched
 * the same endpoint:
 *   - ActiveJobBadge       (cs-shell topbar, every 4 s)
 *   - HistoryTab           (cs-shell history pane, every 5 s)
 *   - RenderWorkflow       (auto-reattach on mount, one-shot)
 *
 * Each had its own setInterval + state. With three components mounted at
 * the same time we ran 3 GET /api/jobs/history calls every 4-5 seconds.
 * Now there is one poll: `startPolling()` arms a single 4 s interval
 * (refcounted across subscribers so it stays alive while any one of them
 * is mounted, and is torn down when the last subscriber unmounts).
 *
 * Subscribers read `items` (full list) and `active` (first running/queued)
 * directly from the store via the standard `useJobsStore(selector)` hook.
 * They can also call `refresh()` to force a fetch outside the interval
 * cycle (e.g. immediately after a cancel/resume action so the UI updates
 * without a 4 s wait).
 */
import { create } from 'zustand'
import { getJobHistory, getQueueStatus } from '@/api/jobs'
import type { HistoryItem } from '@/types/api'

const POLL_MS = 4000

interface JobsStore {
  items: HistoryItem[]
  /** First active (running or queued) job, if any. Convenience accessor
   *  used by ActiveJobBadge + RenderWorkflow auto-reattach. */
  active: HistoryItem | null
  /** Count of running/queued jobs. */
  activeCount: number
  /** Pha 3 — pending job_ids in dispatch order (front-first), from the
   *  scheduler heap. Lets the dock show a queued job's position #N/M. */
  queueOrder: string[]
  /** Pha 3.3b — paused (held) job_ids. Shown as "Paused" instead of a
   *  queue position; not dispatchable until resumed. */
  heldIds: string[]
  loading: boolean
  error: string | null
  /** Number of subscribers currently polling. The interval is alive
   *  while this is > 0. */
  _refcount: number
  _intervalId: ReturnType<typeof setInterval> | null

  refresh: () => Promise<void>
  startPolling: () => void
  stopPolling: () => void
}

async function _fetchAndUpdate(set: (partial: Partial<JobsStore>) => void) {
  try {
    // Queue order is best-effort — a failure there must not blank the
    // history list, so it resolves to null and falls back to [].
    const [res, queue] = await Promise.all([
      getJobHistory(30, 0),
      getQueueStatus().catch(() => null),
    ])
    const items = res.items
    const activeItems = items.filter(
      (j) => j.status === 'running' || j.status === 'queued',
    )
    set({
      items,
      active: activeItems[0] ?? null,
      activeCount: activeItems.length,
      queueOrder: queue?.order ?? [],
      heldIds: queue?.held ?? [],
      error: null,
      loading: false,
    })
  } catch (e) {
    set({
      error: e instanceof Error ? e.message : 'Failed to fetch jobs',
      loading: false,
    })
  }
}

export const useJobsStore = create<JobsStore>((set, get) => ({
  items: [],
  active: null,
  activeCount: 0,
  queueOrder: [],
  heldIds: [],
  loading: false,
  error: null,
  _refcount: 0,
  _intervalId: null,

  refresh: async () => {
    if (!get().loading) set({ loading: true })
    await _fetchAndUpdate(set)
  },

  startPolling: () => {
    const next = get()._refcount + 1
    set({ _refcount: next })
    if (next === 1 && get()._intervalId === null) {
      // First subscriber — kick off an immediate fetch + arm the interval.
      _fetchAndUpdate(set)
      const id = setInterval(() => { _fetchAndUpdate(set) }, POLL_MS)
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

/**
 * Convenience hook for components that want polling lifecycle wired to
 * their mount/unmount. Returns the latest items / active / activeCount.
 */
import { useEffect } from 'react'

export function useActiveJobs() {
  const startPolling = useJobsStore((s) => s.startPolling)
  const stopPolling = useJobsStore((s) => s.stopPolling)
  const items = useJobsStore((s) => s.items)
  const active = useJobsStore((s) => s.active)
  const activeCount = useJobsStore((s) => s.activeCount)
  const loading = useJobsStore((s) => s.loading)
  const error = useJobsStore((s) => s.error)
  const refresh = useJobsStore((s) => s.refresh)

  useEffect(() => {
    startPolling()
    return () => { stopPolling() }
  }, [startPolling, stopPolling])

  return { items, active, activeCount, loading, error, refresh }
}
