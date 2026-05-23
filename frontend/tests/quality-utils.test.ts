/**
 * quality-utils.test.ts — pure logic tests for quality feature helpers.
 */
import { describe, it, expect } from 'vitest'
import {
  getFriendlyTraceLabel,
  getSeverityIcon,
  formatScore,
} from '../src/features/quality/quality.utils'

describe('getFriendlyTraceLabel — known refs', () => {
  it("returns 'AI pacing applied' for 'ai.pacing_applied'", () => {
    expect(getFriendlyTraceLabel('ai.pacing_applied')).toBe('AI pacing applied')
  })

  it("returns 'AI caption emphasis applied' for 'ai.subtitle_emphasis_applied'", () => {
    expect(getFriendlyTraceLabel('ai.subtitle_emphasis_applied')).toBe('AI caption emphasis applied')
  })

  it("returns 'AI visual energy applied' for 'ai.visual_intensity_applied'", () => {
    expect(getFriendlyTraceLabel('ai.visual_intensity_applied')).toBe('AI visual energy applied')
  })

  it("returns 'AI execution hints generated' for 'ai.execution_hints'", () => {
    expect(getFriendlyTraceLabel('ai.execution_hints')).toBe('AI execution hints generated')
  })

  it("returns 'AI decision rejected safely' for 'ai.decision_rejected'", () => {
    expect(getFriendlyTraceLabel('ai.decision_rejected')).toBe('AI decision rejected safely')
  })

  it("returns 'AI validation fix applied' for 'ai.validation_fixup'", () => {
    expect(getFriendlyTraceLabel('ai.validation_fixup')).toBe('AI validation fix applied')
  })
})

describe('getFriendlyTraceLabel — fallback behaviour', () => {
  it('returns a non-empty string for an unknown ref', () => {
    const result = getFriendlyTraceLabel('ai.unknown_event')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('returns a non-empty string for an empty string', () => {
    const result = getFriendlyTraceLabel('')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('formatScore', () => {
  it("formats 87.4 as '87/100'", () => {
    expect(formatScore(87.4)).toBe('87/100')
  })

  it("formats 0 as '0/100'", () => {
    expect(formatScore(0)).toBe('0/100')
  })

  it('rounds 99.9 to 100', () => {
    expect(formatScore(99.9)).toBe('100/100')
  })

  it('rounds 50.5 to 51', () => {
    expect(formatScore(50.5)).toBe('51/100')
  })
})

describe('getSeverityIcon', () => {
  it('returns a non-empty string for critical', () => {
    const icon = getSeverityIcon('critical')
    expect(typeof icon).toBe('string')
    expect(icon.length).toBeGreaterThan(0)
  })

  it('returns a non-empty string for error', () => {
    expect(getSeverityIcon('error').length).toBeGreaterThan(0)
  })

  it('returns a non-empty string for warning', () => {
    expect(getSeverityIcon('warning').length).toBeGreaterThan(0)
  })

  it('returns a non-empty string for info', () => {
    expect(getSeverityIcon('info').length).toBeGreaterThan(0)
  })

  it('returns a non-empty string for unknown severity (graceful fallback)', () => {
    const icon = getSeverityIcon('unknown')
    expect(typeof icon).toBe('string')
    expect(icon.length).toBeGreaterThan(0)
  })
})
