/**
 * T3.1 closure regression guard — Audit 2026-06-08 (Batch A V8-C1).
 *
 * Pre-T3.1 the FE saw only DB-snapshot polling — the structured
 * events from the backend's `_emit_render_event` stream were trapped
 * in JSONL log files. T3.1 added a parallel event channel on the
 * WebSocket: snapshot messages now carry ``type:"snapshot"``, and a
 * new ``type:"event"`` message carries individual log events from
 * the EVENT_BROADCASTER.
 *
 * This file pins the FE side of the closure:
 *
 * 1. `events.ts` exposes `isLogEvent` type guard + `WsLogEvent`
 *    interface — the FE's contract for the new channel.
 *
 * 2. `RenderSocketClient` dispatches on `type:"event"` BEFORE the
 *    `isProgressEvent` check (event messages don't carry job/parts/
 *    summary so they'd fail that guard).
 *
 * 3. `RenderSocketClient` exposes `onLogEvent` registration so
 *    consumers can subscribe to the event channel without
 *    re-implementing the dispatch.
 *
 * 4. `useRenderSocket` hook surfaces `liveEvents: WsLogEvent[]` in
 *    its return type — bounded by `LIVE_EVENTS_CAP` so long renders
 *    that emit hundreds of events don't unbounded-grow the React
 *    state.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { isLogEvent } from '../src/websocket/events'

const EVENTS_PATH = join(__dirname, '..', 'src', 'websocket', 'events.ts')
const CLIENT_PATH = join(__dirname, '..', 'src', 'websocket', 'RenderSocketClient.ts')
const HOOK_PATH = join(__dirname, '..', 'src', 'hooks', 'useRenderSocket.ts')

function readFile(path: string): string {
  return readFileSync(path, 'utf-8')
}

describe('T3.1 — events.ts WsLogEvent interface + type guard', () => {
  it('exports a WsLogEvent interface', () => {
    const source = readFile(EVENTS_PATH)
    expect(source).toMatch(/export\s+interface\s+WsLogEvent\b/)
  })

  it('exports an isLogEvent type guard', () => {
    const source = readFile(EVENTS_PATH)
    expect(source).toMatch(/export\s+function\s+isLogEvent\b/)
  })

  describe('isLogEvent runtime behaviour', () => {
    it("returns true for {type:'event', event:{...}}", () => {
      const msg = {
        type: 'event',
        event: {
          timestamp: '2026-06-08T08:00:00Z',
          level: 'INFO',
          event: 'render.test',
        },
      }
      expect(isLogEvent(msg)).toBe(true)
    })

    it('returns false for snapshot messages', () => {
      const snap = { type: 'snapshot', job: {}, parts: [], summary: {} }
      expect(isLogEvent(snap)).toBe(false)
    })

    it("returns false for ping messages ({type:'ping'})", () => {
      expect(isLogEvent({ type: 'ping' })).toBe(false)
    })

    it('returns false for null / undefined / primitives', () => {
      expect(isLogEvent(null)).toBe(false)
      expect(isLogEvent(undefined)).toBe(false)
      expect(isLogEvent('string')).toBe(false)
      expect(isLogEvent(42)).toBe(false)
    })

    it("returns false when type:'event' but event field missing", () => {
      expect(isLogEvent({ type: 'event' })).toBe(false)
    })
  })
})

describe('T3.1 — RenderSocketClient dispatches on type', () => {
  it('imports isLogEvent + WsLogEvent from events', () => {
    const source = readFile(CLIENT_PATH)
    expect(source).toMatch(/import\s*\{[^}]*\bisLogEvent\b/)
    expect(source).toMatch(/import\s+type\s*\{[^}]*\bWsLogEvent\b/)
  })

  it('defines a LogEventHandler type', () => {
    const source = readFile(CLIENT_PATH)
    expect(source).toMatch(/type\s+LogEventHandler\s*=/)
  })

  it('exposes an onLogEvent method on the client', () => {
    const source = readFile(CLIENT_PATH)
    expect(source).toMatch(/onLogEvent\s*\(/)
  })

  it('owns a logEventHandlers array on the client', () => {
    const source = readFile(CLIENT_PATH)
    expect(source).toMatch(/logEventHandlers\s*:\s*LogEventHandler\[\]/)
  })

  it('dispatches isLogEvent messages BEFORE isProgressEvent', () => {
    const source = readFile(CLIENT_PATH)
    const logCheckIdx = source.search(/\bif\s*\(\s*isLogEvent\s*\(/)
    const progressCheckIdx = source.search(/\bif\s*\(\s*isProgressEvent\s*\(/)
    expect(logCheckIdx).toBeGreaterThan(-1)
    expect(progressCheckIdx).toBeGreaterThan(-1)
    expect(logCheckIdx).toBeLessThan(progressCheckIdx)
    // Comment: event messages don't carry job/parts/summary so they'd
    // fail isProgressEvent — the order matters.
  })

  it('forwards the event payload to every registered handler', () => {
    const source = readFile(CLIENT_PATH)
    // Look for `this.logEventHandlers.forEach((h) => { ... h(msg.event) ... })`
    expect(source).toMatch(/logEventHandlers\.forEach/)
  })

  it('protects against handler exceptions (try/catch inside forEach)', () => {
    const source = readFile(CLIENT_PATH)
    // A handler that throws must NOT kill the WS loop. The dispatch
    // must wrap each handler call in try/catch.
    const dispatchBlock = source.match(/logEventHandlers\.forEach[\s\S]*?\}\s*\)/g)
    expect(dispatchBlock).toBeTruthy()
    const combined = (dispatchBlock ?? []).join('\n')
    expect(combined).toMatch(/\btry\s*\{/)
    expect(combined).toMatch(/\bcatch\b/)
  })
})

describe('T3.1 — useRenderSocket surfaces liveEvents', () => {
  it('imports WsLogEvent from the websocket events module', () => {
    const source = readFile(HOOK_PATH)
    expect(source).toMatch(/import\s+type\s*\{[^}]*\bWsLogEvent\b/)
  })

  it('defines a LIVE_EVENTS_CAP constant for buffer bounding', () => {
    const source = readFile(HOOK_PATH)
    expect(source).toMatch(/LIVE_EVENTS_CAP\s*=\s*\d+/)
  })

  it('declares liveEvents on the RenderSocketState type', () => {
    const source = readFile(HOOK_PATH)
    expect(source).toMatch(/liveEvents\s*:\s*WsLogEvent\[\]/)
  })

  it('uses a useState slot for liveEvents', () => {
    const source = readFile(HOOK_PATH)
    expect(source).toMatch(/useState\s*<\s*WsLogEvent\[\]\s*>/)
  })

  it('registers an onLogEvent handler that buffers via setLiveEvents', () => {
    const source = readFile(HOOK_PATH)
    expect(source).toMatch(/client\.onLogEvent\s*\(/)
    expect(source).toMatch(/setLiveEvents\s*\(/)
  })

  it('bounds the buffer at LIVE_EVENTS_CAP (slice on overflow)', () => {
    const source = readFile(HOOK_PATH)
    // The buffer push MUST trim to the cap to avoid unbounded state
    // growth across long renders that emit hundreds of events.
    expect(source).toMatch(/\.slice\s*\(\s*0\s*,\s*LIVE_EVENTS_CAP\s*\)/)
  })

  it('returns liveEvents from the hook', () => {
    const source = readFile(HOOK_PATH)
    const returnBlock = source.match(/return\s*\{[\s\S]*?\}/g)
    expect(returnBlock).toBeTruthy()
    const combined = (returnBlock ?? []).join('\n')
    expect(combined).toMatch(/\bliveEvents\b/)
  })
})
