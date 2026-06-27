/**
 * render-eta.test.ts — Pha 5.2.
 *
 * estimateRenderEtaSec: throughput model once clips finish, linear fallback
 * before that, null when no estimate is meaningful.
 */
import { describe, it, expect } from 'vitest'
import { estimateRenderEtaSec } from '../src/features/clip-studio/render/eta'

describe('Pha 5.2 — estimateRenderEtaSec', () => {
  it('uses clip throughput once gaps are observed', () => {
    // avg 20s/clip, 3 of 5 remaining → 60s.
    const eta = estimateRenderEtaSec({
      elapsedSec: 999, overallPct: 50, doneCount: 2, totalCount: 5,
      clipIntervalsMs: [20_000, 20_000],
    })
    expect(eta).toBe(60)
  })

  it('throughput overrides the linear estimate (stage-aware)', () => {
    // Linear would say elapsed*(100-pct)/pct = 100*50/50 = 100s, but observed
    // throughput (10s/clip, 2 remaining) says 20s — throughput wins.
    const eta = estimateRenderEtaSec({
      elapsedSec: 100, overallPct: 50, doneCount: 3, totalCount: 5,
      clipIntervalsMs: [10_000, 10_000],
    })
    expect(eta).toBe(20)
  })

  it('returns 0 when all clips are done', () => {
    const eta = estimateRenderEtaSec({
      elapsedSec: 100, overallPct: 100, doneCount: 3, totalCount: 3,
      clipIntervalsMs: [20_000, 20_000],
    })
    expect(eta).toBe(0)
  })

  it('falls back to linear before any clip finishes', () => {
    // No intervals yet → linear: 60 * (100-40)/40 = 90s.
    const eta = estimateRenderEtaSec({
      elapsedSec: 60, overallPct: 40, doneCount: 0, totalCount: 5,
      clipIntervalsMs: [],
    })
    expect(eta).toBe(90)
  })

  it('returns null too early (≤2% and no clips)', () => {
    expect(estimateRenderEtaSec({
      elapsedSec: 2, overallPct: 1, doneCount: 0, totalCount: 5, clipIntervalsMs: [],
    })).toBeNull()
  })

  it('returns null at 100% with no throughput signal', () => {
    expect(estimateRenderEtaSec({
      elapsedSec: 100, overallPct: 100, doneCount: 0, totalCount: 0, clipIntervalsMs: [],
    })).toBeNull()
  })
})
