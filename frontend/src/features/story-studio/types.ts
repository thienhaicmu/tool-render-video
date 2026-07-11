/**
 * types.ts — Story Studio v2 config + constants (Super-Prompt + Cue Sheet).
 *
 * The heavy domain types (StoryPlanV2, Beat, Visual…) live in api/story.ts
 * (they mirror the backend). This file holds the FE-only input config + the enum
 * option lists the review editors (F3) drive their selects from.
 */

export type StoryPhase = 'input' | 'review' | 'monitor'
export type StorySource = 'paste' | 'idea'
export type Aspect = '16:9' | '9:16' | '1:1'

export const STORY_LANGS = [
  { code: 'vi', label: 'Tiếng Việt', locale: 'vi-VN' },
  { code: 'en', label: 'English', locale: 'en-US' },
  { code: 'ja', label: '日本語', locale: 'ja-JP' },
  { code: 'ko', label: '한국어', locale: 'ko-KR' },
] as const
export type StoryLang = typeof STORY_LANGS[number]['code']

// Story UI language → RenderRequest.voice_language locale (backend routes TTS:
// vi/ko→Gemini, en/ja→ElevenLabs via resolve_story_tts_engine).
export const VOICE_LOCALE: Record<StoryLang, 'vi-VN' | 'en-US' | 'ja-JP' | 'ko-KR'> = {
  vi: 'vi-VN', en: 'en-US', ja: 'ja-JP', ko: 'ko-KR',
}

export const ASPECTS: Aspect[] = ['16:9', '9:16', '1:1']
export const ART_STYLE_PRESETS = [
  'wuxia', 'xianxia', 'anime', 'romance', 'realistic', 'ink wash', 'fantasy', 'horror',
] as const
export const GENRE_PRESETS = [
  'tien-hiep', 'huyen-huyen', 'ngon-tinh', 'kiem-hiep', 'do-thi', 'khoa-huyen', 'kinh-di',
] as const

// Cue-sheet enums the TimelineEditor (F3) drives its selects from — mirror the
// backend story_plan_v2 enum tuples.
export const FOCUS = ['wide', 'left', 'center', 'right', 'top', 'bottom', 'close'] as const
export const MOTION = ['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down', 'static'] as const
export const TRANSITION = ['cut', 'fade', 'slide', 'zoom', 'flash', 'to_black'] as const
export const TIER = ['low', 'medium', 'high'] as const

// Phase 2 — FINAL image provider. Draft/review always previews with the free
// provider; this picks what the actual render uses.
export type ImageProvider = 'gpt_image' | 'pollinations'
// Rough per-image cost for the premium provider (gpt-image-1, medium) — used only
// for the FE cost hint on the Render button. Free provider = $0.
export const PREMIUM_IMG_COST_USD = 0.04

/**
 * FE input config. Minimal by design — the AI decides tone / image count / voices.
 * Source A (paste) uses ``chapterText``; source B (idea) uses ``idea`` +
 * ``durationSec``. ``subtitles`` is off by default (voice-only, hook titles burn
 * regardless on the backend).
 */
export interface StoryConfig {
  source: StorySource
  chapterText: string
  idea: string
  durationSec: number      // source=idea target length (UI edits in minutes)
  genre: string
  language: StoryLang
  artStyle: string
  aspect: Aspect
  subtitles: boolean
  seriesId: string
  chapterNo: number
  outputDir: string
  imageProvider: ImageProvider   // FINAL render provider (draft always previews free)
}

export const DEFAULT_STORY_CFG: StoryConfig = {
  source: 'paste',
  chapterText: '',
  idea: '',
  durationSec: 90,
  genre: '',
  language: 'vi',
  artStyle: '',
  aspect: '16:9',
  subtitles: false,
  seriesId: '',
  chapterNo: 0,
  outputDir: '',
  imageProvider: 'gpt_image',    // premium default (Sacred #2 parity); toggle to free
}
