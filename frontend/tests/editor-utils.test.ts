/**
 * editor-utils.test.ts — pure function tests for editor.utils.ts
 */
import { describe, it, expect } from 'vitest'
import {
  buildMediaUrl,
  buildThumbnailUrl,
  formatTime,
  clamp,
  validateTrim,
} from '../src/features/editor/editor.utils'

// ── buildMediaUrl ──────────────────────────────────────────────────────────────

describe('buildMediaUrl', () => {
  it("returns correct URL for simple job ID", () => {
    expect(buildMediaUrl('abc', 1)).toBe('/api/render/jobs/abc/parts/1/media')
  })

  it("encodes special characters in job ID", () => {
    const url = buildMediaUrl('a/b c', 2)
    expect(url).toContain('/api/render/jobs/')
    expect(url).toContain('/parts/2/media')
    // Should be URL-encoded
    expect(url).not.toContain(' ')
  })
})

// ── buildThumbnailUrl ──────────────────────────────────────────────────────────

describe('buildThumbnailUrl', () => {
  it("returns correct thumbnail URL", () => {
    expect(buildThumbnailUrl('abc', 1)).toBe('/api/render/jobs/abc/parts/1/thumbnail')
  })
})

// ── formatTime ────────────────────────────────────────────────────────────────

describe('formatTime', () => {
  it("formats 0 as 0:00", () => {
    expect(formatTime(0)).toBe('0:00')
  })

  it("formats 65 as 1:05", () => {
    expect(formatTime(65)).toBe('1:05')
  })

  it("formats 3600 as 60:00", () => {
    expect(formatTime(3600)).toBe('60:00')
  })

  it("formats 59 as 0:59", () => {
    expect(formatTime(59)).toBe('0:59')
  })

  it("formats 61 as 1:01", () => {
    expect(formatTime(61)).toBe('1:01')
  })

  it("truncates sub-second precision", () => {
    expect(formatTime(65.9)).toBe('1:05')
  })
})

// ── clamp ─────────────────────────────────────────────────────────────────────

describe('clamp', () => {
  it("returns value within range unchanged", () => {
    expect(clamp(5, 0, 10)).toBe(5)
  })

  it("clamps negative below min to min", () => {
    expect(clamp(-1, 0, 10)).toBe(0)
  })

  it("clamps above max to max", () => {
    expect(clamp(15, 0, 10)).toBe(10)
  })

  it("returns min when value equals min", () => {
    expect(clamp(0, 0, 10)).toBe(0)
  })

  it("returns max when value equals max", () => {
    expect(clamp(10, 0, 10)).toBe(10)
  })
})

// ── validateTrim ──────────────────────────────────────────────────────────────

describe('validateTrim', () => {
  it("returns null for valid trim (0 to 30 in 60s video)", () => {
    expect(validateTrim(0, 30, 60)).toBeNull()
  })

  it("returns error when start is negative", () => {
    expect(validateTrim(-1, 30, 60)).not.toBeNull()
  })

  it("returns error when start >= end (start > end)", () => {
    expect(validateTrim(30, 10, 60)).not.toBeNull()
  })

  it("returns error when start === end", () => {
    expect(validateTrim(10, 10, 60)).not.toBeNull()
  })

  it("returns error when trim < 1 second", () => {
    expect(validateTrim(0, 0.5, 60)).not.toBeNull()
  })

  it("returns error when end > duration", () => {
    expect(validateTrim(0, 70, 60)).not.toBeNull()
  })

  it("returns null when end equals duration exactly", () => {
    expect(validateTrim(0, 60, 60)).toBeNull()
  })

  it("returns null for trim of exactly 1 second", () => {
    expect(validateTrim(0, 1, 60)).toBeNull()
  })

  it("allows any end when duration is 0 (not yet loaded)", () => {
    // duration=0 means not yet loaded — don't block on end > duration
    expect(validateTrim(0, 100, 0)).toBeNull()
  })
})
