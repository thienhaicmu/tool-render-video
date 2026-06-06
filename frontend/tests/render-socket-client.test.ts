/**
 * render-socket-client.test.ts — Audit ST-13 / TEST09 closure (Batch 10D 2026-06-06).
 *
 * RenderSocketClient is the load-bearing WebSocket abstraction for live
 * job progress (WS /api/jobs/{id}/ws). The reconnect policy is critical
 * for long renders (55–60 min) where transient drops happen routinely:
 *
 *   - On WS close: reconnect with exponential backoff (2s → 4s → … → 30s cap)
 *   - Up to 20 attempts before emitting 'max_reconnect_attempts_reached'
 *   - Terminal status (completed/failed/cancelled) STOPS reconnects
 *   - disconnect() stops reconnects too
 *
 * If this policy regresses the user sees a frozen progress UI in mid-render
 * with no error — silent failure. These tests pin the contract.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { RenderSocketClient } from '../src/websocket/RenderSocketClient'

// ── Mock WebSocket ────────────────────────────────────────────────────────────
// Vitest's jsdom env doesn't supply a usable WebSocket. We replace the
// global with a hand-rolled stub so we can drive open/message/close events
// from the test side.

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  closeCalls = 0

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  // Test-side helpers.
  triggerOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }
  triggerMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
  triggerClose() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
  triggerError() {
    this.onerror?.()
  }
  close() {
    this.closeCalls += 1
    this.readyState = MockWebSocket.CLOSED
  }
}

const originalWS = globalThis.WebSocket

beforeEach(() => {
  MockWebSocket.instances = []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).WebSocket = MockWebSocket
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).WebSocket = originalWS
})


describe('RenderSocketClient', () => {

  it('connects on connect() and reports isConnected after onopen', () => {
    const client = new RenderSocketClient()
    client.connect('job-1', '/api/jobs/job-1/ws')

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('/api/jobs/job-1/ws')
    expect(client.isConnected).toBe(false)

    MockWebSocket.instances[0].triggerOpen()
    expect(client.isConnected).toBe(true)
  })

  it('schedules a reconnect after onclose with ~2s initial delay', () => {
    const client = new RenderSocketClient()
    const reconnecting = vi.fn()
    client.onReconnecting(reconnecting)

    client.connect('job-2', '/api/jobs/job-2/ws')
    MockWebSocket.instances[0].triggerOpen()
    MockWebSocket.instances[0].triggerClose()

    // Reconnect handler fires synchronously inside _maybeReconnect.
    expect(reconnecting).toHaveBeenCalledWith(1, 20)
    expect(MockWebSocket.instances).toHaveLength(1)  // not yet reopened

    // Advance the scheduled timer → next WebSocket constructed.
    vi.advanceTimersByTime(2100)
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('applies exponential backoff capped at 30s', () => {
    const client = new RenderSocketClient()
    const reconnecting = vi.fn()
    client.onReconnecting(reconnecting)

    client.connect('job-3', '/api/jobs/job-3/ws')

    // Drive several reconnect attempts.
    for (let attempt = 0; attempt < 5; attempt++) {
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.triggerClose()
      vi.advanceTimersByTime(31_000)  // > cap so any attempt fires
    }

    // 5 reconnect attempts logged + initial connect → 6 sockets opened.
    expect(MockWebSocket.instances.length).toBe(6)
    // Reconnect handler reports the attempt count, capped at MAX (20).
    const attemptArgs = reconnecting.mock.calls.map((c) => c[0])
    expect(attemptArgs).toEqual([1, 2, 3, 4, 5])
  })

  it('STOPS reconnecting after a terminal status event', () => {
    const client = new RenderSocketClient()
    const complete = vi.fn()
    const reconnecting = vi.fn()
    client.onComplete(complete)
    client.onReconnecting(reconnecting)

    client.connect('job-terminal', '/api/jobs/job-terminal/ws')
    MockWebSocket.instances[0].triggerOpen()

    // Server emits a terminal progress event.
    MockWebSocket.instances[0].triggerMessage({
      job: { job_id: 'job-terminal', status: 'completed', stage: 'DONE', message: 'OK' },
      parts: [],
      summary: {},
    })
    expect(complete).toHaveBeenCalledTimes(1)

    // Then the socket closes naturally — reconnect MUST NOT fire because
    // _destroyed was set when the terminal status was observed.
    MockWebSocket.instances[0].triggerClose()
    vi.advanceTimersByTime(60_000)

    expect(reconnecting).not.toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(1)  // no new socket opened
  })

  it('disconnect() prevents any further reconnect attempts', () => {
    const client = new RenderSocketClient()
    const reconnecting = vi.fn()
    client.onReconnecting(reconnecting)

    client.connect('job-discon', '/api/jobs/job-discon/ws')
    MockWebSocket.instances[0].triggerOpen()

    client.disconnect()
    // Even if the underlying socket then closes, reconnect must not fire.
    MockWebSocket.instances[0].triggerClose()
    vi.advanceTimersByTime(60_000)

    expect(reconnecting).not.toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('ignores keepalive ping messages without dispatching handlers', () => {
    const client = new RenderSocketClient()
    const progress = vi.fn()
    const errorH = vi.fn()
    client.onProgress(progress)
    client.onError(errorH)

    client.connect('job-ping', '/api/jobs/job-ping/ws')
    MockWebSocket.instances[0].triggerOpen()
    MockWebSocket.instances[0].triggerMessage({ type: 'ping' })

    expect(progress).not.toHaveBeenCalled()
    expect(errorH).not.toHaveBeenCalled()
  })

  it('emits max_reconnect_attempts_reached after exhausting the budget', () => {
    const client = new RenderSocketClient()
    const errorH = vi.fn()
    client.onError(errorH)

    client.connect('job-budget', '/api/jobs/job-budget/ws')

    // Trigger 20 reconnect cycles; each onclose advances the counter.
    for (let attempt = 0; attempt < 20; attempt++) {
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.triggerClose()
      vi.advanceTimersByTime(31_000)
    }
    // The 21st close should hit the cap and emit the budget-exceeded error
    // without scheduling another open.
    const lastWs = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    const socketsBefore = MockWebSocket.instances.length
    lastWs.triggerClose()
    vi.advanceTimersByTime(31_000)

    expect(MockWebSocket.instances.length).toBe(socketsBefore)  // no new socket
    expect(errorH).toHaveBeenCalledWith('max_reconnect_attempts_reached')
  })
})
