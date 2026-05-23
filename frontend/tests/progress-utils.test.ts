/**
 * progress-utils.test.ts — pure logic tests for progress utility functions.
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeProgressPercent,
  getStageLabel,
  getStatusLabel,
  deriveConnectionStatus,
  extractLatestMessage,
  getPartLabel,
} from '../src/features/progress/progress.utils'

// ── normalizeProgressPercent ───────────────────────────────────────────────────

describe('normalizeProgressPercent', () => {
  it('clamps values above 100 to 100', () => {
    expect(normalizeProgressPercent(105)).toBe(100)
  })

  it('clamps negative values to 0', () => {
    expect(normalizeProgressPercent(-5)).toBe(0)
  })

  it('passes through values within range', () => {
    expect(normalizeProgressPercent(50)).toBe(50)
  })

  it('returns 0 for null', () => {
    expect(normalizeProgressPercent(null)).toBe(0)
  })

  it('returns 0 for undefined', () => {
    expect(normalizeProgressPercent(undefined)).toBe(0)
  })

  it('returns 0 at exactly 0', () => {
    expect(normalizeProgressPercent(0)).toBe(0)
  })

  it('returns 100 at exactly 100', () => {
    expect(normalizeProgressPercent(100)).toBe(100)
  })
})

// ── getStageLabel ──────────────────────────────────────────────────────────────

describe('getStageLabel', () => {
  it("maps 'segment_building' to 'Analyzing Scenes'", () => {
    expect(getStageLabel('segment_building')).toBe('Analyzing Scenes')
  })

  it("maps 'rendering' to 'Rendering Parts'", () => {
    expect(getStageLabel('rendering')).toBe('Rendering Parts')
  })

  it("maps 'complete' to 'Complete'", () => {
    expect(getStageLabel('complete')).toBe('Complete')
  })

  it("maps 'starting' to 'Starting'", () => {
    expect(getStageLabel('starting')).toBe('Starting')
  })

  it("maps 'finalizing' to 'Finalizing'", () => {
    expect(getStageLabel('finalizing')).toBe('Finalizing')
  })

  it("maps 'error' to 'Error'", () => {
    expect(getStageLabel('error')).toBe('Error')
  })

  it("maps unknown string to 'Processing'", () => {
    expect(getStageLabel('unknown_xyz')).toBe('Processing')
  })

  it("maps null to 'Processing'", () => {
    expect(getStageLabel(null)).toBe('Processing')
  })

  it("maps undefined to 'Processing'", () => {
    expect(getStageLabel(undefined)).toBe('Processing')
  })

  it("maps empty string to 'Processing'", () => {
    expect(getStageLabel('')).toBe('Processing')
  })
})

// ── getStatusLabel ─────────────────────────────────────────────────────────────

describe('getStatusLabel', () => {
  it("maps 'completed' to 'Complete'", () => {
    expect(getStatusLabel('completed')).toBe('Complete')
  })

  it("maps 'failed' to 'Failed'", () => {
    expect(getStatusLabel('failed')).toBe('Failed')
  })

  it("maps 'cancelling' to 'Canceling...'", () => {
    expect(getStatusLabel('cancelling')).toBe('Canceling...')
  })

  it("maps null to 'Processing'", () => {
    expect(getStatusLabel(null)).toBe('Processing')
  })

  it("maps 'queued' to 'Queued'", () => {
    expect(getStatusLabel('queued')).toBe('Queued')
  })

  it("maps 'running' to 'Rendering'", () => {
    expect(getStatusLabel('running')).toBe('Rendering')
  })

  it("maps 'completed_with_errors' to 'Completed with Errors'", () => {
    expect(getStatusLabel('completed_with_errors')).toBe('Completed with Errors')
  })

  it("maps 'interrupted' to 'Interrupted'", () => {
    expect(getStatusLabel('interrupted')).toBe('Interrupted')
  })

  it("maps 'cancelled' to 'Canceled'", () => {
    expect(getStatusLabel('cancelled')).toBe('Canceled')
  })

  it("maps 'canceled' to 'Canceled'", () => {
    expect(getStatusLabel('canceled')).toBe('Canceled')
  })

  it("maps unknown string to 'Processing'", () => {
    expect(getStatusLabel('some_unknown_status')).toBe('Processing')
  })
})

// ── deriveConnectionStatus ─────────────────────────────────────────────────────

describe('deriveConnectionStatus', () => {
  it("returns 'live' when connected and not terminal", () => {
    expect(deriveConnectionStatus(true, false, null)).toBe('live')
  })

  it("returns 'connecting' when not connected, not terminal, no error", () => {
    expect(deriveConnectionStatus(false, false, null)).toBe('connecting')
  })

  it("returns 'disconnected' when not connected with error", () => {
    expect(deriveConnectionStatus(false, false, 'max_reconnect_attempts_reached')).toBe('disconnected')
  })

  it("returns 'terminal' when isTerminal is true", () => {
    expect(deriveConnectionStatus(false, true, null)).toBe('terminal')
  })

  it("returns 'terminal' even when connected and isTerminal is true", () => {
    expect(deriveConnectionStatus(true, true, null)).toBe('terminal')
  })

  it("returns 'terminal' even when error and isTerminal is true", () => {
    expect(deriveConnectionStatus(false, true, 'some error')).toBe('terminal')
  })
})

// ── extractLatestMessage ───────────────────────────────────────────────────────

describe('extractLatestMessage', () => {
  it("returns '' for empty string", () => {
    expect(extractLatestMessage('')).toBe('')
  })

  it("returns '' for null", () => {
    expect(extractLatestMessage(null)).toBe('')
  })

  it("returns '' for undefined", () => {
    expect(extractLatestMessage(undefined)).toBe('')
  })

  it('returns the message text for a valid string', () => {
    expect(extractLatestMessage('Processing clip 3')).toBe('Processing clip 3')
  })

  it('trims leading/trailing whitespace', () => {
    expect(extractLatestMessage('  some message  ')).toBe('some message')
  })
})

// ── getPartLabel ───────────────────────────────────────────────────────────────

describe('getPartLabel', () => {
  it("returns 'Part 1' for part 1", () => {
    expect(getPartLabel(1)).toBe('Part 1')
  })

  it("returns 'Part 5' for part 5", () => {
    expect(getPartLabel(5)).toBe('Part 5')
  })

  it("returns 'Part 10' for part 10", () => {
    expect(getPartLabel(10)).toBe('Part 10')
  })
})
