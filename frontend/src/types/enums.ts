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

// ── Subtitle style (§6.3) — 10 canonical presets only ────────────────────────
// DO NOT add legacy aliases: pro_karaoke, viral_clean_montserrat, etc.

export type SubtitleStyle =
  | 'tiktok_bounce_v1'
  | 'bold_cap'
  | 'story_clean_01'
  | 'viral_bold'
  | 'clean_pro'
  | 'boxed_caption'
  | 'viral'
  | 'clean'
  | 'story'
  | 'gaming'

export const SUBTITLE_STYLE_VALUES = [
  'tiktok_bounce_v1',
  'bold_cap',
  'story_clean_01',
  'viral_bold',
  'clean_pro',
  'boxed_caption',
  'viral',
  'clean',
  'story',
  'gaming',
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
  | 'failed'
  | 'interrupted'
  | 'cancelled'
  | 'cancelling'

export const TERMINAL_JOB_STATUSES: readonly JobStatusEnum[] = [
  'completed',
  'completed_with_errors',
  'failed',
  'interrupted',
  'cancelled',
] as const

export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_JOB_STATUSES as readonly string[]).includes(status)
}

// ── WebSocket render stages ───────────────────────────────────────────────────

export type RenderStage =
  | 'starting'
  | 'segment_building'
  | 'rendering'
  | 'finalizing'
  | 'complete'
  | 'error'

// ── Quality severity levels (§8.4) ───────────────────────────────────────────

export type IssueSeverity = 'critical' | 'error' | 'warning' | 'info'
