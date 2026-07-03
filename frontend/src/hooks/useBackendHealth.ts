/**
 * useBackendHealth — refcounted shared poller for backend liveness +
 * Whisper warmup state. Same pattern as useSystemResources so multiple
 * subscribers (Studio status bar, AppShell topbar) share one 30 s poll
 * instead of fanning out duplicate GETs.
 *
 * P0.1 (frontend redesign): the Studio status bar previously hardcoded
 * its API/FFmpeg/Whisper dots as always-green while Topbar ran its own
 * real /health check. This hook is now the single source of truth.
 *
 *   apiOk        null = not measured yet · true/false = last /health result
 *   whisperReady null = unknown · true once /api/warmup/status reports
 *                loaded/ready (fetch skipped after that — model stays warm)
 */
import { create } from 'zustand'
import { useEffect } from 'react'
import { apiFetch } from '../api/client'
import { isTabHidden } from './pollVisibility'

const POLL_MS = 30_000

interface WarmupStatus {
  model?: string
  status?: string
  loaded?: boolean
  ready?: boolean
}

interface HealthStore {
  apiOk: boolean | null
  whisperReady: boolean | null
  warmupStatus: WarmupStatus | null
  _refcount: number
  _intervalId: ReturnType<typeof setInterval> | null
  startPolling: () => void
  stopPolling: () => void
}

async function _fetchAndUpdate(
  set: (partial: Partial<HealthStore>) => void,
  get: () => HealthStore,
) {
  try {
    await apiFetch('/health')
    set({ apiOk: true })
  } catch {
    // Backend unreachable — warmup state is unknowable too.
    set({ apiOk: false, whisperReady: null, warmupStatus: null })
    return
  }
  // Warmup is a one-way transition; stop re-fetching once ready.
  if (get().whisperReady === true) return
  try {
    const data = await apiFetch<WarmupStatus>('/api/warmup/status')
    set({
      warmupStatus: data,
      whisperReady: !!(data.loaded || data.ready),
    })
  } catch {
    // warmup status unavailable — not critical, leave as unknown
  }
}

export const useHealthStore = create<HealthStore>((set, get) => ({
  apiOk: null,
  whisperReady: null,
  warmupStatus: null,
  _refcount: 0,
  _intervalId: null,

  startPolling: () => {
    const next = get()._refcount + 1
    set({ _refcount: next })
    if (next === 1 && get()._intervalId === null) {
      _fetchAndUpdate(set, get)
      const id = setInterval(() => { if (isTabHidden()) return; _fetchAndUpdate(set, get) }, POLL_MS)
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

export function useBackendHealth() {
  const startPolling = useHealthStore((s) => s.startPolling)
  const stopPolling  = useHealthStore((s) => s.stopPolling)
  const apiOk        = useHealthStore((s) => s.apiOk)
  const whisperReady = useHealthStore((s) => s.whisperReady)
  const warmupStatus = useHealthStore((s) => s.warmupStatus)

  useEffect(() => {
    startPolling()
    return () => { stopPolling() }
  }, [startPolling, stopPolling])

  return { apiOk, whisperReady, warmupStatus }
}
