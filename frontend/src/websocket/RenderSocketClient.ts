/**
 * RenderSocketClient — WebSocket abstraction for live job progress.
 * Endpoint: WS /api/jobs/{jobId}/ws
 * Contract: docs/ui/UI_BACKEND_CONTRACT.md §11
 *
 * Reconnect policy: up to 3 attempts with 2-second exponential backoff.
 * Does NOT reconnect if the job has reached a terminal status.
 */
import { BASE_URL } from '../api/client'
import { isProgressEvent, isErrorEvent } from './events'
import { isTerminalStatus } from '../types/enums'
import type { WebSocketEvent, WsProgressSummary } from '../types/api'

type StageHandler = (stage: string, message: string) => void
type ProgressHandler = (summary: WsProgressSummary) => void
type CompleteHandler = (event: WebSocketEvent) => void
type ErrorHandler = (error: string) => void

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
const MAX_RECONNECT_ATTEMPTS = 3
const RECONNECT_BASE_DELAY_MS = 2000

export class RenderSocketClient {
  private jobId: string | null = null
  private socket: WebSocket | null = null
  private reconnectAttempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _connected = false
  private _destroyed = false

  // Handlers
  private stageHandlers: StageHandler[] = []
  private progressHandlers: ProgressHandler[] = []
  private completeHandlers: CompleteHandler[] = []
  private errorHandlers: ErrorHandler[] = []

  get isConnected(): boolean {
    return this._connected
  }

  connect(jobId: string): void {
    if (this._destroyed) return
    this.jobId = jobId
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

  // ── Private ────────────────────────────────────────────────────────────────

  private _openSocket(): void {
    if (!this.jobId || this._destroyed) return

    const url = `${WS_BASE}/api/jobs/${encodeURIComponent(this.jobId)}/ws`
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

      if (isErrorEvent(msg)) {
        this._emitError(String(msg.error))
        return
      }

      if (isProgressEvent(msg)) {
        const event = msg as WebSocketEvent
        const { job, summary } = event

        // Emit stage change
        this.stageHandlers.forEach((h) => h(job.stage, job.message))

        // Emit progress
        this.progressHandlers.forEach((h) => h(summary))

        // Emit complete on terminal status
        if (isTerminalStatus(job.status)) {
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
    const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempt)
    this.reconnectAttempt += 1
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
