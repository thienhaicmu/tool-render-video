/**
 * RenderSocketClient — WebSocket abstraction for live job progress.
 * Endpoint: WS /api/jobs/{jobId}/ws
 * Contract: docs/ui/UI_BACKEND_CONTRACT.md §11
 *
 * Reconnect policy: up to MAX_RECONNECT_ATTEMPTS with exponential backoff
 * capped at MAX_RECONNECT_DELAY_MS.  Does NOT reconnect if the job has
 * reached a terminal status.
 *
 * Keepalive: the backend sends {"type":"ping"} every 25 s during long renders.
 * The client silently ignores these — they exist solely to keep TCP alive.
 */
import { BASE_URL } from '../api/client'
import { isProgressEvent, isErrorEvent, isLogEvent } from './events'
import type { WsLogEvent } from './events'
import { isTerminalStatus } from '../types/enums'
import type { WebSocketEvent, WsProgressSummary } from '../types/api'

type StageHandler = (stage: string, message: string) => void
type ProgressHandler = (summary: WsProgressSummary, parts: import('../types/api').JobPart[]) => void
type CompleteHandler = (event: WebSocketEvent) => void
type ErrorHandler = (error: string) => void
type ReconnectingHandler = (attempt: number, maxAttempts: number) => void
// T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). Live log/structured
// event bridged from EVENT_BROADCASTER on the backend.
type LogEventHandler = (event: WsLogEvent) => void

function computeWsBase(): string {
  if (BASE_URL) {
    return BASE_URL.replace(/^http/, 'ws')
  }
  // Same-origin: derive from current page location
  if (typeof window !== 'undefined') {
    return window.location.origin.replace(/^http/, 'ws')
  }
  // Fallback for tests/SSR
  return 'ws://127.0.0.1:8000'
}
const WS_BASE = computeWsBase()
// 20 attempts covers ~20 minutes of retries (2s → 4s → … → 30s cap).
// Long renders (55–60 min) can experience transient drops; 3 was too few.
const MAX_RECONNECT_ATTEMPTS = 20
const RECONNECT_BASE_DELAY_MS = 2000
const MAX_RECONNECT_DELAY_MS = 30_000

export class RenderSocketClient {
  private jobId: string | null = null
  private socket: WebSocket | null = null
  private reconnectAttempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _connected = false
  private _destroyed = false
  private _wsUrlOverride: string | null = null

  // Handlers
  private stageHandlers: StageHandler[] = []
  private progressHandlers: ProgressHandler[] = []
  private completeHandlers: CompleteHandler[] = []
  private errorHandlers: ErrorHandler[] = []
  private reconnectingHandlers: ReconnectingHandler[] = []
  // T3.1 — log/structured event handlers.
  private logEventHandlers: LogEventHandler[] = []

  get isConnected(): boolean {
    return this._connected
  }

  connect(jobId: string, wsUrlOverride?: string): void {
    if (this._destroyed) return
    this.jobId = jobId
    this._wsUrlOverride = wsUrlOverride ?? null
    this.reconnectAttempt = 0
    this._openSocket()
  }

  disconnect(): void {
    this._destroyed = true
    this._clearReconnectTimer()
    this._closeSocket()
  }

  onStageChange(handler: StageHandler): void {
    this.stageHandlers.push(handler)
  }

  onProgress(handler: ProgressHandler): void {
    this.progressHandlers.push(handler)
  }

  onComplete(handler: CompleteHandler): void {
    this.completeHandlers.push(handler)
  }

  onError(handler: ErrorHandler): void {
    this.errorHandlers.push(handler)
  }

  onReconnecting(handler: ReconnectingHandler): void {
    this.reconnectingHandlers.push(handler)
  }

  /**
   * T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). Register a
   * handler for live structured/log events bridged from the
   * backend's ``_emit_render_event`` stream via EVENT_BROADCASTER.
   * Pre-T3.1 these events were trapped in JSONL log files — now
   * they flow live alongside the snapshot poll. Consumers can use
   * them to render an "AI activity" panel, a live log view, or
   * surface specific event types (e.g. ``render.plan.ai_emitted``).
   */
  onLogEvent(handler: LogEventHandler): void {
    this.logEventHandlers.push(handler)
  }

  // ── Private ────────────────────────────────────────────────────────────────

  private _openSocket(): void {
    if (!this.jobId || this._destroyed) return

    const url = this._wsUrlOverride
      ? `${WS_BASE}${this._wsUrlOverride}`
      : `${WS_BASE}/api/jobs/${encodeURIComponent(this.jobId)}/ws`
    const ws = new WebSocket(url)
    this.socket = ws

    ws.onopen = () => {
      this._connected = true
      this.reconnectAttempt = 0
    }

    ws.onmessage = (ev) => {
      let msg: unknown
      try {
        msg = JSON.parse(ev.data as string)
      } catch {
        return
      }

      // Ignore server-side keepalive pings ({"type":"ping"}) — they exist
      // solely to prevent proxy/OS from tearing down idle TCP connections.
      if (msg && typeof msg === 'object' && (msg as Record<string, unknown>).type === 'ping') {
        return
      }

      if (isErrorEvent(msg)) {
        this._emitError(String(msg.error))
        return
      }

      // T3.1 — Dispatch on the new ``type:"event"`` message before the
      // progress-event check. Log events DO NOT carry job/parts/summary
      // so they would fail isProgressEvent; we route them to the
      // dedicated log-event channel here.
      if (isLogEvent(msg)) {
        this.logEventHandlers.forEach((h) => {
          try {
            h(msg.event)
          } catch {
            // A handler that throws must NOT kill the WS loop. The
            // structured event channel is best-effort.
          }
        })
        return
      }

      if (isProgressEvent(msg)) {
        const event = msg as WebSocketEvent
        const { job, summary } = event

        // Emit stage change
        this.stageHandlers.forEach((h) => h(job.stage, job.message))

        // Emit progress
        this.progressHandlers.forEach((h) => h(summary, event.parts ?? []))

        // Emit complete on terminal status and stop reconnects
        if (isTerminalStatus(job.status)) {
          this._destroyed = true
          this.completeHandlers.forEach((h) => h(event))
        }
      }
    }

    ws.onclose = () => {
      this._connected = false
      this.socket = null
      this._maybeReconnect()
    }

    ws.onerror = () => {
      // onclose fires immediately after onerror — reconnect handled there
      this._connected = false
    }
  }

  private _closeSocket(): void {
    this._connected = false
    if (this.socket) {
      try {
        this.socket.close()
      } catch {
        // ignore
      }
      this.socket = null
    }
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private _maybeReconnect(): void {
    if (this._destroyed) return
    if (this.reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
      this._emitError('max_reconnect_attempts_reached')
      return
    }
    const rawDelay = RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempt)
    const delay = Math.min(rawDelay, MAX_RECONNECT_DELAY_MS)
    this.reconnectAttempt += 1
    this.reconnectingHandlers.forEach((h) => h(this.reconnectAttempt, MAX_RECONNECT_ATTEMPTS))
    this.reconnectTimer = setTimeout(() => {
      if (!this._destroyed) {
        this._openSocket()
      }
    }, delay)
  }

  private _emitError(error: string): void {
    this.errorHandlers.forEach((h) => h(error))
  }
}
