/**
 * loadResults — terminal results fetch orchestration extracted from
 * RenderWorkflow (god-file slice 3).
 *
 * On a terminal job the workflow loads parts, the quality summary and the AI
 * ranking, each behind a 12 s timeout so a slow endpoint can't hang the
 * screen. The original inlined effect set React state directly inside each
 * promise; because the results grid stays behind a loading spinner until ALL
 * three settle (Promise.all → allDataLoaded), collecting the results into one
 * object and applying them together is visually equivalent — and testable.
 *
 * Fields are OPTIONAL on purpose: a field is present only when its fetch
 * succeeded within the timeout, so the caller sets state only for what loaded
 * (a timed-out fetch leaves the previous value untouched, matching the
 * original behaviour).
 */
import { getJobParts, getJobQualitySummary, getJobRanking } from '@/api/jobs'
import type { JobPart, QualityReport, PartRankResult } from '@/types/api'

export interface TerminalResults {
  parts?: JobPart[]
  quality?: {
    scores: Record<number, number>
    reports: Record<number, QualityReport | null>
  }
  /** true only when the quality fetch failed. */
  qualityLoadFailed?: boolean
  partRanks?: Record<number, PartRankResult>
}

export async function loadTerminalResults(jobId: string): Promise<TerminalResults> {
  const withTimeout = <T,>(p: Promise<T>, ms: number): Promise<T | undefined> =>
    Promise.race([p, new Promise<undefined>((resolve) => setTimeout(resolve, ms))])

  const out: TerminalResults = {}

  const partsP = getJobParts(jobId).then((p) => { out.parts = p })
  const qualityP = getJobQualitySummary(jobId, true)
    .then((summary) => {
      const scores: Record<number, number> = {}
      const reports: Record<number, QualityReport | null> = {}
      summary.parts?.forEach((p) => {
        scores[p.part_no] = p.score
        reports[p.part_no] = p.report ?? null
      })
      out.quality = { scores, reports }
    })
    .catch(() => { out.qualityLoadFailed = true })
  const rankingP = getJobRanking(jobId).then((r) => { out.partRanks = r }).catch(() => {})

  await Promise.all([
    withTimeout(partsP, 12_000),
    withTimeout(qualityP, 12_000),
    withTimeout(rankingP, 12_000),
  ])
  return out
}
