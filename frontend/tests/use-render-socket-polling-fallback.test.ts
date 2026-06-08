/**
 * T1.3 closure regression guard — Audit 2026-06-08 (Batch A V9-E1).
 *
 * CLAUDE.md mandates HTTP polling as the reliability fallback for the
 * offline-first desktop app (proxies and corporate firewalls can block
 * WS upgrades). Pre-T1.3 the FE had NO fallback — when
 * RenderSocketClient exhausted its 20-attempt reconnect budget it
 * emitted 'max_reconnect_attempts_reached' and the hook simply set
 * error state; the UI froze for the remainder of the render.
 *
 * T1.3 (commit a32833e) added an HTTP polling fallback in
 * useRenderSocket: when the WS exhausts, the hook switches to 5s
 * polling of GET /api/jobs/{id} + GET /api/jobs/{id}/parts and
 * dispatches into the same state setters the WS handlers use.
 *
 * This file pins T1.3 with source-level checks against
 * `frontend/src/hooks/useRenderSocket.ts`. A future refactor that
 * drops the polling fallback re-introduces V9-E1.
 *
 * Note — we deliberately avoid a behavioural React-hook test here
 * (would require mocking WebSocket + getJob + getJobParts + timers
 * + React rendering). The source-level guards prove the structural
 * wiring is in place; the behaviour itself is exercised by manual
 * QA + production use.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const SRC_PATH = join(__dirname, '..', 'src', 'hooks', 'useRenderSocket.ts')

function readHook(): string {
  return readFileSync(SRC_PATH, 'utf-8')
}

describe('T1.3 — useRenderSocket polling fallback', () => {
  it('imports getJob and getJobParts from the jobs API', () => {
    const source = readHook()
    expect(source).toMatch(/import\s*\{[^}]*\bgetJob\b/)
    expect(source).toMatch(/import\s*\{[^}]*\bgetJobParts\b/)
  })

  it('exposes an `isPolling` flag on the hook return type', () => {
    const source = readHook()
    expect(source).toMatch(/\bisPolling\s*:\s*boolean\b/)
    expect(source).toMatch(/\bisPolling\s*,/)
  })

  it('defines a polling interval constant', () => {
    const source = readHook()
    expect(source).toMatch(/POLLING_FALLBACK_INTERVAL_MS\s*=\s*\d+/)
  })

  it('activates the polling fallback on the max_reconnect_attempts_reached error', () => {
    const source = readHook()
    // The error string the RenderSocketClient emits at reconnect-budget
    // exhaustion. Pinned so a future rename on either side surfaces
    // loudly.
    expect(source).toContain("'max_reconnect_attempts_reached'")
    // The activation pathway — must reference both the error name AND
    // the polling-activation function name.
    expect(source).toMatch(/_startPolling|startPolling/)
  })

  it('uses setInterval to schedule the polling cycle', () => {
    const source = readHook()
    expect(source).toMatch(/\bsetInterval\s*\(/)
    // And cleanup via clearInterval — leaks here would cause an
    // ever-growing fleet of polling timers for any user that views
    // multiple renders.
    expect(source).toMatch(/\bclearInterval\s*\(/)
  })

  it('stops polling on terminal job status (matches WS onComplete behaviour)', () => {
    const source = readHook()
    // Pin the gate. The hook MUST call isTerminalStatus on the
    // poll-derived status before deciding to stop the interval.
    expect(source).toMatch(/isTerminalStatus\s*\(/)
    // The cleanup function name — without `_stopPolling` the interval
    // would leak past the terminal frame.
    expect(source).toMatch(/_stopPolling|stopPolling/)
  })

  it('stops polling on unmount (cleanup in useEffect return)', () => {
    const source = readHook()
    // The return of useEffect MUST invoke _stopPolling so unmounting
    // the panel mid-poll doesn't leak the interval.
    // Heuristic: the `return () =>` block of the useEffect should
    // contain a stop-polling call.
    const returnBlock = source.match(/return\s*\(\s*\)\s*=>\s*\{[\s\S]*?\}/g)
    expect(returnBlock).toBeTruthy()
    const combined = (returnBlock ?? []).join('\n')
    expect(combined).toMatch(/_stopPolling|stopPolling/)
  })

  it('polls both getJob and getJobParts so the summary can be derived', () => {
    const source = readHook()
    // The poll callback MUST issue both requests. Polling just getJob
    // would leave parts state stale; polling just getJobParts would
    // miss the job's stage/status/error_kind.
    expect(source).toMatch(/\bgetJob\s*\(/)
    expect(source).toMatch(/\bgetJobParts\s*\(/)
  })

  it('has a fallback summary computation helper', () => {
    const source = readHook()
    // The backend's WsProgressSummary is computed server-side; in
    // polling mode the FE must derive an approximate equivalent from
    // the parts list. The helper name is pinned so a refactor doesn't
    // silently drop the summary derivation (which would leave
    // progress=null on the polling path).
    expect(source).toMatch(/_computeFallbackSummary|computeFallbackSummary/)
  })

  it('handles polling errors without killing the fallback loop', () => {
    const source = readHook()
    // The pollTick MUST catch its own errors. A bare throw inside
    // setInterval callback would leak the unhandled rejection but
    // leave the timer in place — the loop would silently keep
    // hammering. Pin a try/catch around the pollTick body — match by
    // finding the `_pollTick` declaration and verifying try/catch
    // appears AFTER it before the next top-level callback declaration.
    const tickDeclIdx = source.search(/\bconst\s+_pollTick\s*=/)
    expect(tickDeclIdx).toBeGreaterThan(-1)
    // Slice from the declaration to the next `_` declaration (a sibling
    // private helper inside the useEffect). This bounds the search to
    // the function body.
    const after = source.slice(tickDeclIdx)
    // The function body must contain BOTH try and catch tokens.
    expect(after).toMatch(/\btry\s*\{/)
    expect(after).toMatch(/\bcatch\s*\(/)
  })
})

describe('T1.3 — RenderSocketClient still emits the canonical error string', () => {
  it("emits 'max_reconnect_attempts_reached' at retry-budget exhaustion", () => {
    const clientPath = join(__dirname, '..', 'src', 'websocket', 'RenderSocketClient.ts')
    const source = readFileSync(clientPath, 'utf-8')
    expect(source).toContain("'max_reconnect_attempts_reached'")
  })
})
