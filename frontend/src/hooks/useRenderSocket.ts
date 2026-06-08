/**
 * useRenderSocket — React hook wrapping RenderSocketClient.
 *
 * Cleans up on unmount. Does not reconnect for terminal job states.
 *
 * T1.3 — Audit 2026-06-08 closure (Batch A V9-E1 — CLAUDE.md mandated
 * HTTP polling fallback). When the WebSocket exhausts its reconnect
 * budget (20 attempts, ~20 min of retries), the hook automatically
 * switches to 5-second HTTP polling of GET /api/jobs/{id} +
 * GET /api/jobs/{id}/parts. Progress, parts, stage, and terminal
 * status continue to update; the user is NOT left with a frozen UI
 * when a proxy or corporate firewall blocks the WS upgrade.
 *
 * The poll-derived ``WsProgressSummary`` is approximate compared to
 * the backend's ``_compute_progress_summary`` (the stuck-part window
 * detection requires timestamp diffing that we don't replicate
 * client-side), but it carries enough fidelity for the UI to keep
 * moving. Polling stops on terminal status and on unmount.
 */
import { useEffect, useRef, useState } from 'react'
import { RenderSocketClient } from '../websocket/RenderSocketClient'
import type { WsLogEvent } from '../websocket/events'
import { isTerminalStatus } from '../types/enums'
import { useRenderStore } from '../stores/renderStore'
import { getJob, getJobParts } from '../api/jobs'
import type { JobStatus, WsProgressSummary, JobPart, JobErrorKind } from '../types/api'

const POLLING_FALLBACK_INTERVAL_MS = 5_000
const PART_IN_PROGRESS_STATUSES = ['cutting', 'transcribing', 'rendering', 'waiting'] as const
// T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). Cap the live-event
// buffer at a small number — the UI consumes the latest events and
// older ones drop off. The BE side already drops oldest under
// backpressure (asyncio.Queue(maxsize=200) on the broadcaster); this
// cap is the FE-side equivalent for memory boundedness during long
// renders that emit hundreds of events.
const LIVE_EVENTS_CAP = 50

/**
 * Derive an approximate WsProgressSummary from parts + job. Used when
 * the HTTP polling fallback is active and the backend's exact
 * computation isn't available over the wire.
 */
function _computeFallbackSummary(parts: JobPart[], job: JobStatus | null): WsProgressSummary {
  const total = parts.length
  const completed = parts.filter((p) => p.status === 'done').length
  const failed = parts.filter((p) => p.status === 'failed').length
  const pending = parts.filter((p) => p.status === 'queued').length
  const inProgress = parts.filter((p) => (PART_IN_PROGRESS_STATUSES as readonly string[]).includes(p.status))
  const overallPct = total > 0
    ? Math.round(parts.reduce((s, p) => s + (p.progress_percent || 0), 0) / total)
    : 0
  const partsPct = total > 0 ? Math.round((completed / total) * 100) : 0
  return {
    total_parts: total,
    completed_parts: completed,
    failed_parts: failed,
    pending_parts: pending,
    processing_parts: inProgress.length,
    in_progress_count: inProgress.length,
    active_parts: inProgress.map((p) => ({
      part_no: p.part_no,
      status: p.status,
      progress_percent: p.progress_percent || 0,
    })),
    stuck_parts: [],  // not computable without per-tick timestamp tracking
    current_part: inProgress[0]?.part_no ?? null,
    current_stage: job?.stage ?? null,
    overall_progress_percent: overallPct,
    parts_percent: partsPct,
  }
}

export interface RenderSocketState {
  stage: string | null
  jobStatus: string | null      // from job.status on terminal events
  jobMessage: string | null     // from job.message (second arg of onStageChange)
  progress: WsProgressSummary | null
  liveParts: JobPart[]          // per-event parts array (all parts, current state)
  isConnected: boolean
  isReconnecting: boolean       // true while attempting to re-establish a dropped connection
  isPolling: boolean            // T1.3 — true while HTTP polling fallback is active
  isTerminal: boolean           // derived from jobStatus
  error: string | null
  errorKind: JobErrorKind | null  // structured error classification, set on FAILED
  // T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). Live log /
  // structured events bridged from the backend's _emit_render_event
  // stream. Newest event at index 0; older events drop off the end
  // when the buffer reaches LIVE_EVENTS_CAP.
  liveEvents: WsLogEvent[]
}

export function useRenderSocket(jobId: string | null, wsPathOverride?: string): RenderSocketState {
  const clientRef    = useRef<RenderSocketClient | null>(null)
  const progressRef  = useRef<string>('')   // fingerprint to skip no-op updates
  const partsRef     = useRef<string>('')
  // T1.3 — polling fallback timer + cancellation flag (refs avoid
  // re-running the useEffect when polling state changes).
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollingActiveRef = useRef<boolean>(false)

  const [stage, setStage]           = useState<string | null>(null)
  const [jobStatus, setJobStatus]   = useState<string | null>(null)
  const [jobMessage, setJobMessage] = useState<string | null>(null)
  const [progress, setProgress]     = useState<WsProgressSummary | null>(null)
  const [liveParts, setLiveParts]   = useState<JobPart[]>([])
  const [isConnected, setIsConnected]       = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [isPolling, setIsPolling]           = useState(false)
  const [error, setError]                   = useState<string | null>(null)
  const [errorKind, setErrorKind]           = useState<JobErrorKind | null>(null)
  // T3.1 — live events bridged from backend EVENT_BROADCASTER.
  const [liveEvents, setLiveEvents] = useState<WsLogEvent[]>([])

  const updateJobStatus = useRenderStore((s) => s.updateJobStatus)

  useEffect(() => {
    if (!jobId) return

    const client = new RenderSocketClient()
    clientRef.current = client

    // ── T1.3 — HTTP polling fallback (audit 2026-06-08 V9-E1) ─────────────
    // Called when the WS exhausts its reconnect budget. Polls
    // GET /api/jobs/{id} + GET /api/jobs/{id}/parts every
    // POLLING_FALLBACK_INTERVAL_MS, dispatches into the same state
    // setters the WS handlers use. Stops on terminal status, on
    // unmount, or if an external caller marks the WS connected again
    // (defensive — currently the WS doesn't recover post-exhaustion,
    // but the guard keeps the state machine clean).
    const _stopPolling = () => {
      if (pollingTimerRef.current !== null) {
        clearInterval(pollingTimerRef.current)
        pollingTimerRef.current = null
      }
      pollingActiveRef.current = false
      setIsPolling(false)
    }

    const _pollTick = async () => {
      if (!jobId || !pollingActiveRef.current) return
      try {
        const [job, parts] = await Promise.all([
          getJob(jobId),
          getJobParts(jobId),
        ])
        // Stage + message — same setters as WS onStageChange.
        setStage(job.stage)
        setJobMessage(job.message)
        // Progress + parts — compute approximate summary client-side.
        const summary = _computeFallbackSummary(parts, job)
        const pKey = `${summary.overall_progress_percent}|${summary.completed_parts}|${summary.failed_parts}|${summary.active_parts.length}`
        if (pKey !== progressRef.current) {
          progressRef.current = pKey
          setProgress(summary)
        }
        const partsKey = parts.map((p) => `${p.part_no}:${p.status}:${p.progress_percent}`).join(',')
        if (partsKey !== partsRef.current) {
          partsRef.current = partsKey
          setLiveParts(parts)
        }
        // Terminal handling — same effect as WS onComplete.
        if (isTerminalStatus(job.status)) {
          setJobStatus(job.status)
          setErrorKind(job.error_kind ?? null)
          updateJobStatus(jobId, job.status)
          _stopPolling()
        }
      } catch (err) {
        // Surface the polling failure but keep retrying — a transient
        // 5xx or network blip shouldn't kill the fallback. The user
        // will see error state via the existing setError pathway.
        setError(err instanceof Error ? err.message : 'polling_error')
      }
    }

    const _startPolling = () => {
      if (pollingActiveRef.current) return
      pollingActiveRef.current = true
      setIsPolling(true)
      setIsReconnecting(false)
      // Fire one immediate tick so the UI updates without waiting a
      // full interval after the WS exhausts.
      void _pollTick()
      pollingTimerRef.current = setInterval(_pollTick, POLLING_FALLBACK_INTERVAL_MS)
    }

    client.onStageChange((s, msg) => {
      setStage(s)
      setIsConnected(true)
      setIsReconnecting(false)
      setJobMessage(msg)
      // WS came back up — kill any active polling fallback.
      if (pollingActiveRef.current) _stopPolling()
    })

    client.onProgress((summary, parts) => {
      // Only trigger re-render if data materially changed
      const pKey = `${summary.overall_progress_percent}|${summary.completed_parts}|${summary.failed_parts}|${summary.active_parts}`
      if (pKey !== progressRef.current) {
        progressRef.current = pKey
        setProgress(summary)
      }
      if (parts.length > 0) {
        const partsKey = parts.map(p => `${p.part_no}:${p.status}:${p.progress_percent}`).join(',')
        if (partsKey !== partsRef.current) {
          partsRef.current = partsKey
          setLiveParts(parts)
        }
      }
    })

    client.onComplete((event) => {
      const status = event.job.status
      setJobStatus(status)
      setErrorKind(event.job.error_kind ?? null)
      setIsConnected(false)
      // Sync terminal status into the store so any component reading store sees correct state
      updateJobStatus(jobId, status)
      // Defensive — if polling somehow started before the WS's terminal
      // frame, stop it now.
      if (pollingActiveRef.current) _stopPolling()
    })

    client.onReconnecting(() => {
      setIsConnected(false)
      setIsReconnecting(true)
    })

    // T3.1 — push live structured events into the bounded buffer.
    // Newest event at index 0; older events drop off the tail when
    // the cap is reached. Use functional setState so concurrent
    // pushes don't lose entries between re-renders.
    client.onLogEvent((evt) => {
      setLiveEvents((prev) => {
        const next = [evt, ...prev]
        return next.length > LIVE_EVENTS_CAP ? next.slice(0, LIVE_EVENTS_CAP) : next
      })
    })

    client.onError((err) => {
      setError(err)
      setIsConnected(false)
      setIsReconnecting(false)
      // T1.3 — WS reached its retry budget (RenderSocketClient emits
      // 'max_reconnect_attempts_reached' after 20 attempts) or hit a
      // non-recoverable failure. Switch to HTTP polling so the UI
      // doesn't freeze for the rest of the render.
      if (err === 'max_reconnect_attempts_reached' && !pollingActiveRef.current) {
        _startPolling()
      }
    })

    client.connect(jobId, wsPathOverride)

    return () => {
      client.disconnect()
      clientRef.current = null
      _stopPolling()
    }
  }, [jobId, wsPathOverride, updateJobStatus])

  return {
    stage,
    jobStatus,
    jobMessage,
    progress,
    liveParts,
    isConnected,
    isReconnecting,
    isPolling,
    isTerminal: isTerminalStatus(jobStatus ?? ''),
    error,
    errorKind,
    liveEvents,
  }
}
