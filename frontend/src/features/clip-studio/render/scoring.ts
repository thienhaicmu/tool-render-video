/**
 * scoring — A3: ONE place for score thresholds. Previously aiTier
 * (85/70/55) and the ring/bar colors (70/40 in some spots, 70/50 in
 * others) were separate literal tables that could drift on edit.
 */
export const TIER_VIRAL = 85
export const TIER_HIGH = 70
export const TIER_GOOD = 55

/** Traffic-light color for a 0-100 score. */
export function scoreColor(score: number): string {
  return score >= TIER_HIGH ? 'var(--ok)' : score >= 50 ? 'var(--warn)' : 'var(--fail)'
}
