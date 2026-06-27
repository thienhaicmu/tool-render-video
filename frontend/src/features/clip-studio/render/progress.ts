/**
 * Render display progress — Pha 5.6.
 *
 * The backend's `overall_progress_percent` is the mean of per-clip part
 * progress. It sits at 0 through the entire pre-render phase (analyze /
 * transcribe / scene-detect / segment-build, when no parts exist yet) and
 * then jumps once parts appear — a jarring bar.
 *
 * For a smoother bar we map the current job stage to a base floor and let the
 * parts progress fill the render portion (30 → 100%). This is a DISPLAY-only
 * transform; the raw backend number (consumed elsewhere, incl. AI signals) is
 * left untouched.
 */
export function stageBlendedPercent(stage: string, overallPct: number): number {
  const p = Math.max(0, Math.min(100, overallPct))
  const s = (stage || '').toLowerCase()

  if (s === 'done') return 100
  // Render / write-report: parts progress drives the upper 70% of the bar.
  if (s.includes('render') || s.includes('writing')) return Math.round(30 + p * 0.7)
  // Pre-render phases advance through fixed floors.
  if (s.includes('segment')) return 28
  if (s.includes('scene')) return 22
  if (s.includes('transcrib')) return 15
  if (s.includes('analyz')) return 5
  if (s.includes('download')) return 3
  // Unknown / very early — fall back to the raw parts percent.
  return Math.round(p)
}
