/**
 * Enum constants derived from docs/ui/UI_BACKEND_CONTRACT.md §6
 * These are the EXACT backend values — do not add aliases or legacy names.
 */

// ── Platform (§6.1) ───────────────────────────────────────────────────────────

export type Platform = 'tiktok' | 'youtube_shorts' | 'instagram_reels'

export const PLATFORM_VALUES = ['tiktok', 'youtube_shorts', 'instagram_reels'] as const

// ── Aspect ratio (§6.2) ───────────────────────────────────────────────────────

export type AspectRatio = '9:16' | '3:4' | '1:1' | '16:9' | '4:3'

export const ASPECT_RATIO_VALUES = ['9:16', '3:4', '1:1', '16:9', '4:3'] as const

// ── Subtitle style (§6.3) — 5 CapCut/Opus presets (ass_capcut engine) ────────
// Legacy IDs are still accepted by the backend (aliased) but not offered here.

export type SubtitleStyle =
  | 'opus_pop'
  | 'capcut_box'
  | 'punch_green'
  | 'karaoke_clean'
  | 'smooth_premiere'

export const SUBTITLE_STYLE_VALUES = [
  'opus_pop',
  'capcut_box',
  'punch_green',
  'karaoke_clean',
  'smooth_premiere',
] as const

// ── Effect preset (§6.4) — 6 presets ─────────────────────────────────────────

export type EffectPreset =
  | 'slay_soft_01'
  | 'slay_pop_01'
  | 'story_clean_01'
  | 'social_bright'
  | 'cinematic_soft'
  | 'high_contrast'

export const EFFECT_PRESET_VALUES = [
  'slay_soft_01',
  'slay_pop_01',
  'story_clean_01',
  'social_bright',
  'cinematic_soft',
  'high_contrast',
] as const

// ── Source quality mode (§6.5) ────────────────────────────────────────────────

export type QualityMode = 'standard_1080' | 'high_1440' | 'best_available'

export const QUALITY_MODE_VALUES = ['standard_1080', 'high_1440', 'best_available'] as const

// ── Render profile (§6.6) ─────────────────────────────────────────────────────

export type RenderProfile = 'fast' | 'balanced' | 'quality' | 'best'

export const RENDER_PROFILE_VALUES = ['fast', 'balanced', 'quality', 'best'] as const

// ── Job status values (§9) ────────────────────────────────────────────────────

export type JobStatusEnum =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_errors'
  | 'partial'
  | 'failed'
  | 'interrupted'
  | 'cancelled'
  | 'cancelling'

export const TERMINAL_JOB_STATUSES: readonly JobStatusEnum[] = [
  'completed',
  'completed_with_errors',
  'partial',
  'failed',
  'interrupted',
  'cancelled',
] as const

export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_JOB_STATUSES as readonly string[]).includes(status)
}

// ── WebSocket render stages ───────────────────────────────────────────────────

export type RenderStage =
  | 'queued'
  | 'starting'
  | 'running'
  | 'analyzing'
  | 'downloading'
  | 'scene_detection'
  | 'segment_building'
  | 'transcribing_full'
  | 'rendering'
  | 'rendering_parallel'
  | 'writing_report'
  | 'done'
  | 'failed'
  | 'cancelled'
  // legacy values kept for backward compat
  | 'finalizing'
  | 'complete'
  | 'error'

// ── FE↔BE contract mirror (C1) ────────────────────────────────────────────────
// These three arrays MUST stay byte-identical to the backend canonical
// declaration in backend/app/core/contracts.py. The parity test
// backend/tests/test_fe_be_contract_parity.py fails CI if they drift.
// Do NOT add legacy aliases here (the RenderStage union above may carry
// legacy values for render tolerance; these arrays are the exact wire set).

// Frozen job-stage names — Sacred Contract #4 (mirrors JobStage).
export const JOB_STAGE_VALUES = [
  'queued',
  'starting',
  'running',
  'analyzing',
  'downloading',
  'scene_detection',
  'segment_building',
  'transcribing_full',
  'rendering',
  'rendering_parallel',
  'writing_report',
  'done',
  'failed',
  'cancelled',
] as const

// Frozen per-part status names — Sacred Contract #5 (mirrors JobPartStage).
export type JobPartStageEnum =
  | 'queued'
  | 'waiting'
  | 'cutting'
  | 'transcribing'
  | 'rendering'
  | 'done'
  | 'failed'
  | 'skipped'

export const JOB_PART_STAGE_VALUES = [
  'queued',
  'waiting',
  'cutting',
  'transcribing',
  'rendering',
  'done',
  'failed',
  'skipped',
] as const

// Sacred Contract #1 — keys that MUST exist in every result_json blob.
export const RESULT_JSON_REQUIRED_KEYS = [
  'output_rank_score',
  'is_best_output',
  'is_best_clip',
] as const

// ── Quality severity levels (§8.4) ───────────────────────────────────────────

export type IssueSeverity = 'critical' | 'error' | 'warning' | 'info'
