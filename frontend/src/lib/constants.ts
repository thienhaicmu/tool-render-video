/**
 * Centralized option sets from docs/ui/UI_BACKEND_CONTRACT.md §6
 * All values are exact backend enum strings.
 */

// ── Platforms (§6.1) — 3 items ────────────────────────────────────────────────

export const PLATFORMS = [
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube_shorts', label: 'YouTube Shorts' },
  { value: 'instagram_reels', label: 'Instagram Reels' },
] as const

export type PlatformValue = typeof PLATFORMS[number]['value']

// ── Target Markets — geographic AI knowledge targeting ────────────────────────

export const MARKETS = [
  { value: 'us',    label: '🇺🇸 US',          description: 'Hook 3s · fast cut · viral bold' },
  { value: 'eu',    label: '🇪🇺 Europe',       description: 'Authenticity · slower pacing · story' },
  { value: 'jp',    label: '🇯🇵 Japan',        description: 'Visual hook · silent viewing · clean sub' },
  { value: 'sea',   label: '🌏 SE Asia',       description: 'Entertainment-first · audio-on · local' },
  { value: 'kr',    label: '🇰🇷 Korea',        description: 'Music-driven · K-content · captions' },
  { value: 'latam', label: '🌎 Latin America', description: 'High energy · fast cut · ES/PT sub' },
  { value: 'in',    label: '🇮🇳 India',        description: 'Edutainment · multi-language · Reels/Shorts' },
] as const

export type MarketValue = typeof MARKETS[number]['value']

// ── Aspect ratios (§6.2) — 5 items ───────────────────────────────────────────

export const ASPECT_RATIOS = [
  { value: '9:16', label: '9:16 Vertical', description: 'Full-screen vertical (TikTok native)' },
  { value: '3:4',  label: '3:4 Portrait',  description: 'Default — portrait, safe for all platforms' },
  { value: '1:1',  label: '1:1 Square',    description: 'Square format' },
  { value: '16:9', label: '16:9 Landscape', description: 'Standard widescreen' },
  { value: '4:3',  label: '4:3 Standard',  description: 'Classic TV ratio' },
] as const

export type AspectRatioValue = typeof ASPECT_RATIOS[number]['value']

// ── Subtitle styles (§6.3) — 10 canonical presets ────────────────────────────
// DO NOT include legacy aliases (pro_karaoke, viral_clean_montserrat, etc.)

export const SUBTITLE_STYLES = [
  { value: 'tiktok_bounce_v1', label: 'TikTok Bounce',   description: 'Classic bounce, Bungee font, outline shadow' },
  { value: 'bold_cap',         label: 'Bold Cap',         description: 'Bold, large Bungee, auto-scale' },
  { value: 'story_clean_01',   label: 'Story Clean',      description: 'Montserrat, soft bounce, editorial' },
  { value: 'viral_bold',       label: 'Viral Bold',       description: 'Bold Bungee, boosted size, karaoke highlight' },
  { value: 'clean_pro',        label: 'Clean Pro',        description: 'Inter font, clean professional look' },
  { value: 'boxed_caption',    label: 'Boxed Caption',    description: 'Opaque box behind text, no bounce' },
  { value: 'viral',            label: 'Viral',            description: 'Anton font, 50px, thick outline, TikTok native' },
  { value: 'clean',            label: 'Clean',            description: 'Inter, minimal outline, wide margins' },
  { value: 'story',            label: 'Story',            description: 'Montserrat, cinematic, emotional content' },
  { value: 'gaming',           label: 'Gaming',           description: 'Anton, box-backed, fast-motion readability' },
] as const

export type SubtitleStyleValue = typeof SUBTITLE_STYLES[number]['value']

// ── Effect presets (§6.4) — 6 presets ────────────────────────────────────────

export const EFFECT_PRESETS = [
  { value: 'slay_soft_01',   label: 'Natural Cinematic', description: 'Default — natural look, light sharpening' },
  { value: 'slay_pop_01',    label: 'High Energy',       description: 'Boosted contrast/saturation/unsharp' },
  { value: 'story_clean_01', label: 'Story Clean',       description: 'Subtle — low contrast/saturation, soft sharpening' },
  { value: 'social_bright',  label: 'Social Bright',     description: 'High saturation, strong brightness' },
  { value: 'cinematic_soft', label: 'Cinematic Soft',    description: 'Desaturated, soft, denoised' },
  { value: 'high_contrast',  label: 'High Contrast',     description: 'Maximum contrast, heaviest unsharp' },
] as const

export type EffectPresetValue = typeof EFFECT_PRESETS[number]['value']

// ── Quality modes (§6.5) — 3 items ───────────────────────────────────────────

export const QUALITY_MODES = [
  { value: 'standard_1080',  label: 'Standard 1080p',  description: 'Default — safe, fast download' },
  { value: 'high_1440',      label: 'High 1440p',      description: 'Higher quality, larger file' },
  { value: 'best_available', label: 'Best Available',  description: 'Highest quality yt-dlp can fetch' },
] as const

export type QualityModeValue = typeof QUALITY_MODES[number]['value']

// ── Render profiles (§6.6) — 4 items ─────────────────────────────────────────

export const RENDER_PROFILES = [
  { value: 'fast',     label: 'Fast' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'quality',  label: 'Quality' },
  { value: 'best',     label: 'Best' },
] as const

export type RenderProfileValue = typeof RENDER_PROFILES[number]['value']

// ── Quality score thresholds (§8.3) ──────────────────────────────────────────

export const QUALITY_SCORE_THRESHOLDS = {
  GOOD: 85,
  NEEDS_REVIEW: 70,
  WARNING: 50,
} as const

export type QualityLabel = 'Good' | 'Needs Review' | 'Warning' | 'Poor'
export type QualityVariant = 'success' | 'warning' | 'error' | 'neutral'

export function getQualityLabel(score: number): QualityLabel {
  if (score >= QUALITY_SCORE_THRESHOLDS.GOOD) return 'Good'
  if (score >= QUALITY_SCORE_THRESHOLDS.NEEDS_REVIEW) return 'Needs Review'
  if (score >= QUALITY_SCORE_THRESHOLDS.WARNING) return 'Warning'
  return 'Poor'
}

export function getQualityVariant(score: number): QualityVariant {
  if (score >= QUALITY_SCORE_THRESHOLDS.GOOD) return 'success'
  if (score >= QUALITY_SCORE_THRESHOLDS.NEEDS_REVIEW) return 'warning'
  if (score >= QUALITY_SCORE_THRESHOLDS.WARNING) return 'error'
  return 'neutral'
}

// ── Reframe modes (motion_aware_crop tracking strategy) ──────────────────────

export const REFRAME_MODES = [
  { value: 'subject', label: 'Subject (Face + Body)', description: 'Tracks the main person in frame — face and body detection' },
  { value: 'motion',  label: 'Motion',                description: 'Legacy pixel-difference motion tracking' },
] as const

export type ReframeModeValue = typeof REFRAME_MODES[number]['value']

// ── Validation helpers ────────────────────────────────────────────────────────

/** Clamp playback_speed to [0.5, 1.5] per §6.7 */
export function clampPlaybackSpeed(value: number): number {
  return Math.max(0.5, Math.min(1.5, value))
}

/** Validate playback_speed is within allowed range */
export function isValidPlaybackSpeed(value: number): boolean {
  return value >= 0.5 && value <= 1.5
}
