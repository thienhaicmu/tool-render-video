/**
 * Render ETA estimation — Pha 5.2.
 *
 * The overall progress percent advances at very different rates across the
 * render stages (transcribe is slow, encode is fast, etc.), so extrapolating
 * a single linear "elapsed × (100-pct)/pct" is misleading and jumps around.
 *
 * Better model: once clips start *finishing* (the dominant render phase), we
 * observe the real per-clip cadence and project the remaining clips from it.
 * Before any clip finishes we fall back to the linear estimate, which is the
 * best we can do during analyze/transcribe.
 */
export interface EtaInput {
  elapsedSec: number
  overallPct: number
  doneCount: number
  totalCount: number
  /** Wall-clock gaps (ms) between consecutive clip completions. */
  clipIntervalsMs: number[]
}

/**
 * Returns the estimated seconds remaining, or null when no meaningful
 * estimate is possible yet (too early / no signal).
 */
export function estimateRenderEtaSec(input: EtaInput): number | null {
  const { elapsedSec, overallPct, doneCount, totalCount, clipIntervalsMs } = input

  // Throughput model — needs at least one measured gap (i.e. ≥2 clips done)
  // and a known total. Remaining clips × average observed cadence.
  if (totalCount > 0 && clipIntervalsMs.length >= 1) {
    const avgMs =
      clipIntervalsMs.reduce((a, b) => a + b, 0) / clipIntervalsMs.length
    const remaining = Math.max(0, totalCount - doneCount)
    const sec = Math.round((remaining * avgMs) / 1000)
    return sec >= 0 ? sec : null
  }

  // Linear fallback for the early phases (before clips finish). Mirrors the
  // previous behaviour so the estimate doesn't disappear pre-render.
  if (overallPct > 2 && overallPct < 100) {
    const sec = Math.round((elapsedSec * (100 - overallPct)) / overallPct)
    return sec > 0 ? sec : null
  }

  return null
}
