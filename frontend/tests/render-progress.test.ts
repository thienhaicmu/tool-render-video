/**
 * render-progress.test.ts — Pha 5.6.
 *
 * stageBlendedPercent: pre-render stages advance through fixed floors, the
 * render stage blends parts progress into 30→100, done = 100.
 */
import { describe, it, expect } from 'vitest'
import { stageBlendedPercent } from '../src/features/clip-studio/render/progress'

describe('Pha 5.6 — stageBlendedPercent', () => {
  it('advances through pre-render floors regardless of parts pct', () => {
    expect(stageBlendedPercent('analyzing', 0)).toBe(5)
    expect(stageBlendedPercent('transcribing_full', 0)).toBe(15)
    expect(stageBlendedPercent('scene_detection', 0)).toBe(22)
    expect(stageBlendedPercent('segment_building', 0)).toBe(28)
  })

  it('blends parts progress into the render portion (30→100)', () => {
    expect(stageBlendedPercent('rendering', 0)).toBe(30)
    expect(stageBlendedPercent('rendering', 50)).toBe(65)
    expect(stageBlendedPercent('rendering', 100)).toBe(100)
    expect(stageBlendedPercent('rendering_parallel', 50)).toBe(65)
    expect(stageBlendedPercent('writing_report', 100)).toBe(100)
  })

  it('done is always 100', () => {
    expect(stageBlendedPercent('done', 0)).toBe(100)
  })

  it('falls back to raw percent for unknown/early stages', () => {
    expect(stageBlendedPercent('queued', 0)).toBe(0)
    expect(stageBlendedPercent('', 12)).toBe(12)
  })

  it('clamps out-of-range input', () => {
    expect(stageBlendedPercent('rendering', 150)).toBe(100)
    expect(stageBlendedPercent('rendering', -10)).toBe(30)
  })
})
