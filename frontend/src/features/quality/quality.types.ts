/**
 * quality.types.ts — local types and display maps for the quality feature module.
 */

export type QualityLoadState = 'idle' | 'loading' | 'loaded' | 'error' | 'not_available'

/** Friendly display names for AI trace ref event types. */
export const AI_TRACE_FRIENDLY: Record<string, string> = {
  'ai.pacing_applied': 'AI pacing applied',
  'ai.subtitle_emphasis_applied': 'AI caption emphasis applied',
  'ai.visual_intensity_applied': 'AI visual energy applied',
  'ai.execution_hints': 'AI execution hints generated',
  'ai.decision_rejected': 'AI decision rejected safely',
  'ai.validation_fixup': 'AI validation fix applied',
}
