/**
 * helpers.ts — pure PlanReview helpers (kept out of index.tsx so index and the
 * TimelineEditor can both import them without a circular dependency).
 */
import type { Beat, Visual } from '../../../api/story'
import { beatLines } from '../../../api/story'

const CPS: Record<string, number> = { vi: 15, en: 14, ja: 8, ko: 9 }
const PALETTE = ['#e0567a', '#4f9dde', '#4fbf87', '#d9a441', '#9b6cd6', '#e08a4f', '#46b8c4', '#c14fa0']

/** Per-beat estimated seconds — mirror backend StoryPlan.beat_est_sec (sums lines). */
export function beatEstSec(b: Beat, language: string): number {
  const chars = beatLines(b).reduce((s, l) => s + (l.text || '').trim().length, 0)
  if (!chars) return Math.max(0, b.hold_sec || 0)
  const cps = CPS[(language || 'vi').slice(0, 2)] ?? 14
  return chars / cps / (b.reading_speed || 1)
}

/** Stable colour per visual (index-based) for the timeline badges. */
export function visualColorMap(visuals: Visual[]): Record<string, string> {
  const m: Record<string, string> = {}
  visuals.forEach((v, i) => { m[v.id] = PALETTE[i % PALETTE.length] })
  return m
}
