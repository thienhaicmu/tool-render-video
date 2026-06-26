/**
 * useJobCompletionNotifier — fires an OS notification when a job
 * transitions from running/queued into a terminal state.
 *
 * Why this exists: render jobs run 20-60 minutes. Users alt-tab. In-app
 * toasts auto-dismiss in 5 s, so a finished render produces no surface
 * the user can find when they come back. This hook bridges the gap by
 * invoking the Electron preload `notify()` IPC; the web build is a no-op.
 *
 * Click handling: when the user clicks an OS notification, the main
 * process emits `notify-clicked` with { jobId, kind }. We attach the job
 * to renderStore.activeJobId and navigate to the relevant panel so the
 * user lands on the live progress / results view.
 */
import { useEffect, useRef } from 'react'
import { useActiveJobs } from '../stores/jobsStore'
import { useUIStore } from '../stores/uiStore'
import { useRenderStore } from '../stores/renderStore'
import { isTerminalStatus } from '../types/enums'
import type { HistoryItem, JobStatus } from '../types/api'

function formatTitle(item: HistoryItem): string {
  const kind = item.kind === 'render' ? 'Render' : 'Download'
  const status = item.status
  if (status === 'completed' || status === 'completed_with_errors') return `${kind} hoàn tất`
  if (status === 'partial') return `${kind} hoàn tất (một số clip lỗi)`
  if (status === 'failed') return `${kind} thất bại`
  if (status === 'cancelled') return `${kind} đã hủy`
  if (status === 'interrupted') return `${kind} bị gián đoạn`
  return `${kind} ${status}`
}

function formatBody(item: HistoryItem): string {
  const title = item.title || item.source_hint || item.job_id.slice(0, 8)
  if (item.kind === 'render' && item.total_count) {
    const done = item.completed_count || 0
    const failed = item.failed_count || 0
    if (failed > 0) return `${title} · ${done}/${item.total_count} clips ok, ${failed} lỗi`
    return `${title} · ${done}/${item.total_count} clips`
  }
  return title
}

export function useJobCompletionNotifier() {
  // Subscribing via useActiveJobs guarantees the shared 4 s poll is alive
  // as long as the notifier is mounted, independent of whether the dock
  // is also mounted.
  const { items } = useActiveJobs()
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)

  // Map<job_id, last-seen status>. Used to diff transitions across polls.
  const prevStatuses = useRef<Map<string, string> | null>(null)

  // Fire OS notifications on terminal transitions.
  useEffect(() => {
    const electronAPI = (window as Window & { electronAPI?: { notify?: (opts: { title: string; body?: string; jobId?: string; kind?: 'render' | 'download' }) => Promise<{ ok: boolean }> } }).electronAPI
    const notify = electronAPI?.notify

    // First-ever update: bootstrap the map without firing notifications for
    // jobs that were already terminal before the user opened the app.
    if (prevStatuses.current === null) {
      const initial = new Map<string, string>()
      for (const item of items) initial.set(item.job_id, item.status)
      prevStatuses.current = initial
      return
    }

    const prev = prevStatuses.current
    const next = new Map<string, string>()

    for (const item of items) {
      next.set(item.job_id, item.status)
      const before = prev.get(item.job_id)
      const becameTerminal =
        before !== undefined &&
        !isTerminalStatus(before) &&
        isTerminalStatus(item.status)
      if (becameTerminal && notify) {
        void notify({
          title: formatTitle(item),
          body: formatBody(item),
          jobId: item.job_id,
          kind: item.kind,
        })
      }
    }

    prevStatuses.current = next
  }, [items])

  // Subscribe to notification clicks (lifetime of the app).
  useEffect(() => {
    const electronAPI = (window as Window & {
      electronAPI?: {
        onNotificationClicked?: (
          handler: (payload: { jobId: string | null; kind: string | null }) => void,
        ) => () => void
      }
    }).electronAPI
    const subscribe = electronAPI?.onNotificationClicked
    if (!subscribe) return

    const unsubscribe = subscribe(({ jobId, kind }) => {
      if (jobId && kind === 'render') {
        useRenderStore.setState((state) => {
          if (state.jobs[jobId]) {
            return { activeJobId: jobId }
          }
          // Synthesize a stub entry so RenderWorkflow can attach. The store
          // will be overwritten by the next WS snapshot once attached.
          const stub: JobStatus = {
            job_id: jobId,
            kind: 'render',
            status: 'completed',
            stage: '',
            progress_percent: 100,
            message: '',
            payload_json: '',
            result_json: '',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          } as JobStatus
          return {
            activeJobId: jobId,
            jobs: { ...state.jobs, [jobId]: stub },
          }
        })
        // Pha 4 — open the job's Monitor explicitly (the broad auto-reattach
        // that used to do this on panel switch is gone).
        setMonitorJobId(jobId)
        setActivePanel('clip-studio')
      } else if (jobId && kind === 'download') {
        setActivePanel('download')
      }
    })

    return unsubscribe
  }, [setActivePanel, setMonitorJobId])
}
