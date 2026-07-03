/**
 * scoreView — single source of truth for the Results "display score" and
 * clip sort order (WP3). Previously the `output_rank_score ?? quality` rule
 * and the viral/duration/newest sort were inlined in StepResults in several
 * places, which risked drift between the card, the detail panel and the ring.
 */
import type { JobPart, PartRankResult } from '@/types/api'

export type SortMode = 'viral' | 'duration' | 'newest'

/** The one display score for a clip: AI rank score when present, else the
 *  QA/quality score. Returns undefined when neither exists. */
export function displayScore(
  rank: PartRankResult | undefined,
  qualityScore: number | undefined,
): number | undefined {
  return rank?.output_rank_score ?? qualityScore
}

/** Sort finished clips for the Results grid. 'viral' = AI rank order when a
 *  ranking exists, else quality score descending. */
export function sortDoneParts(
  doneParts: JobPart[],
  sortMode: SortMode,
  partRanks: Record<number, PartRankResult>,
  partScores: Record<number, number>,
): JobPart[] {
  const hasRanks = Object.keys(partRanks).length > 0
  return [...doneParts].sort((a, b) =>
    sortMode === 'duration'
      ? (b.duration ?? 0) - (a.duration ?? 0)
      : sortMode === 'newest'
        ? b.part_no - a.part_no
        : hasRanks
          ? (partRanks[a.part_no]?.output_rank ?? 999) - (partRanks[b.part_no]?.output_rank ?? 999)
          : (partScores[b.part_no] ?? 0) - (partScores[a.part_no] ?? 0)
  )
}
