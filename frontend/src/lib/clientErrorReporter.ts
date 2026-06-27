/**
 * Client error reporter — B2 follow-up (2026-06-27).
 *
 * Forwards uncaught renderer errors and unhandled promise rejections to the
 * backend (`POST /api/client/error`), which records them in the structured
 * `data/logs/errors.jsonl` sink alongside backend errors. Hard renderer
 * crashes (process gone) cannot be caught here — those are reported by the
 * Electron main process in `desktop-shell/main.js`.
 *
 * Contract: fire-and-forget, never throws, and self-throttles so an error
 * loop can never flood the backend or recurse through its own failures.
 */
import { BASE_URL } from '../api/client'

const ENDPOINT = `${BASE_URL}/api/client/error`

// Hard cap per session — a render/render-loop bug can fire onerror in a
// tight loop; we record the first N then go silent until reload.
const MAX_REPORTS_PER_SESSION = 50
let _sent = 0

interface ClientErrorPayload {
  source: 'renderer'
  kind: 'error' | 'unhandledrejection'
  message: string
  stack: string
  url: string
}

function send(payload: ClientErrorPayload): void {
  if (_sent >= MAX_REPORTS_PER_SESSION) return
  _sent += 1
  try {
    // keepalive lets the report survive an unload; errors are swallowed so
    // the reporter can never itself raise (which would re-enter onerror).
    void fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* never throw */
  }
}

function truncate(s: unknown, max = 16_000): string {
  const str = typeof s === 'string' ? s : String(s ?? '')
  return str.length > max ? str.slice(0, max) : str
}

let _initialised = false

export function initClientErrorReporter(): void {
  if (_initialised || typeof window === 'undefined') return
  _initialised = true

  window.addEventListener('error', (e: ErrorEvent) => {
    send({
      source: 'renderer',
      kind: 'error',
      message: truncate(e.message || e.error?.message || 'unknown error'),
      stack: truncate(e.error?.stack ?? ''),
      url: window.location.href,
    })
  })

  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    const reason = e.reason
    send({
      source: 'renderer',
      kind: 'unhandledrejection',
      message: truncate(reason?.message ?? reason ?? 'unhandled rejection'),
      stack: truncate(reason?.stack ?? ''),
      url: window.location.href,
    })
  })
}
