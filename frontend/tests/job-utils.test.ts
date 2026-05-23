/**
 * job-utils.test.ts — tests for jobs utility functions.
 */
import { describe, it, expect } from 'vitest'
import {
  formatRelativeTime,
  isTerminalStatus,
  isActiveStatus,
  canCancel,
  canRetry,
  canDelete,
} from '../src/features/jobs/jobs.utils'
import type { HistoryItem } from '../src/types/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    job_id: 'job-1',
    kind: 'render',
    status: 'completed',
    stage: 'done',
    title: 'Test job',
    source_hint: null,
    timestamp: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_dir: null,
    completed_count: 1,
    failed_count: 0,
    unsupported_count: 0,
    total_count: 1,
    summary_text: '1 part done',
    can_open_folder: false,
    can_retry: false,
    can_rerun: false,
    ...overrides,
  }
}

// ── isTerminalStatus ──────────────────────────────────────────────────────────

describe('isTerminalStatus', () => {
  it('returns true for completed', () => {
    expect(isTerminalStatus('completed')).toBe(true)
  })

  it('returns true for partial', () => {
    expect(isTerminalStatus('partial')).toBe(true)
  })

  it('returns true for failed', () => {
    expect(isTerminalStatus('failed')).toBe(true)
  })

  it('returns true for cancelled', () => {
    expect(isTerminalStatus('cancelled')).toBe(true)
  })

  it('returns true for interrupted', () => {
    expect(isTerminalStatus('interrupted')).toBe(true)
  })

  it('returns false for running', () => {
    expect(isTerminalStatus('running')).toBe(false)
  })

  it('returns false for queued', () => {
    expect(isTerminalStatus('queued')).toBe(false)
  })

  it('returns false for cancelling', () => {
    expect(isTerminalStatus('cancelling')).toBe(false)
  })
})

// ── isActiveStatus ────────────────────────────────────────────────────────────

describe('isActiveStatus', () => {
  it('returns true for running', () => {
    expect(isActiveStatus('running')).toBe(true)
  })

  it('returns true for queued', () => {
    expect(isActiveStatus('queued')).toBe(true)
  })

  it('returns true for cancelling', () => {
    expect(isActiveStatus('cancelling')).toBe(true)
  })

  it('returns false for completed', () => {
    expect(isActiveStatus('completed')).toBe(false)
  })

  it('returns false for failed', () => {
    expect(isActiveStatus('failed')).toBe(false)
  })
})

// ── canCancel ─────────────────────────────────────────────────────────────────

describe('canCancel', () => {
  it('returns true for a running item', () => {
    expect(canCancel(makeItem({ status: 'running' }))).toBe(true)
  })

  it('returns true for a queued item', () => {
    expect(canCancel(makeItem({ status: 'queued' }))).toBe(true)
  })

  it('returns false for a completed item', () => {
    expect(canCancel(makeItem({ status: 'completed' }))).toBe(false)
  })

  it('returns false for a failed item', () => {
    expect(canCancel(makeItem({ status: 'failed' }))).toBe(false)
  })
})

// ── canRetry ──────────────────────────────────────────────────────────────────

describe('canRetry', () => {
  it('returns true when item.can_retry=true', () => {
    expect(canRetry(makeItem({ can_retry: true }))).toBe(true)
  })

  it('returns false when item.can_retry=false', () => {
    expect(canRetry(makeItem({ can_retry: false }))).toBe(false)
  })
})

// ── canDelete ─────────────────────────────────────────────────────────────────

describe('canDelete', () => {
  it('returns true for completed', () => {
    expect(canDelete(makeItem({ status: 'completed' }))).toBe(true)
  })

  it('returns true for partial', () => {
    expect(canDelete(makeItem({ status: 'partial' }))).toBe(true)
  })

  it('returns true for failed', () => {
    expect(canDelete(makeItem({ status: 'failed' }))).toBe(true)
  })

  it('returns true for cancelled', () => {
    expect(canDelete(makeItem({ status: 'cancelled' }))).toBe(true)
  })

  it('returns true for interrupted', () => {
    expect(canDelete(makeItem({ status: 'interrupted' }))).toBe(true)
  })

  it('returns false for running', () => {
    expect(canDelete(makeItem({ status: 'running' }))).toBe(false)
  })

  it('returns false for queued', () => {
    expect(canDelete(makeItem({ status: 'queued' }))).toBe(false)
  })
})

// ── formatRelativeTime ────────────────────────────────────────────────────────

describe('formatRelativeTime', () => {
  it('returns "just now" for a very recent timestamp', () => {
    const recent = new Date(Date.now() - 3000).toISOString() // 3 seconds ago
    expect(formatRelativeTime(recent)).toBe('just now')
  })

  it('returns seconds-based string for ~30 seconds ago', () => {
    const ts = new Date(Date.now() - 30_000).toISOString()
    const result = formatRelativeTime(ts)
    expect(result).toMatch(/seconds ago/)
  })

  it('returns minutes-based string for ~2 minutes ago', () => {
    const ts = new Date(Date.now() - 2 * 60 * 1000).toISOString()
    const result = formatRelativeTime(ts)
    expect(result).toMatch(/minute/)
  })

  it('returns hours-based string for ~2 hours ago', () => {
    const ts = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
    const result = formatRelativeTime(ts)
    expect(result).toMatch(/hour/)
    expect(result).toMatch(/ago/)
  })

  it('returns days-based string for an old timestamp', () => {
    const ts = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    const result = formatRelativeTime(ts)
    expect(result).toMatch(/day/)
    expect(result).toMatch(/ago/)
  })
})
