/**
 * types.ts — shared types + constants for the Story Studio.
 * Mirrors the Content Studio structure (types split from the phase components).
 */
import type { Ratio } from '../clip-studio/render/types'

export type StoryPhase = 'input' | 'bible' | 'storyboard'

export const STORY_LANGS = [
  { code: 'vi', label: 'Tiếng Việt', locale: 'vi-VN' },
  { code: 'en', label: 'English', locale: 'en-US' },
  { code: 'ja', label: '日本語', locale: 'ja-JP' },
] as const
export type StoryLang = typeof STORY_LANGS[number]['code']

export const STORY_RATIOS: Ratio[] = ['r916', 'r11', 'r169']
export const READING_PACES = ['slow', 'normal', 'fast'] as const
export type ReadingPace = typeof READING_PACES[number]
export const STORY_SUB_STYLES = ['auto', 'opus_pop', 'capcut_box', 'punch_green', 'karaoke_clean', 'smooth_premiere'] as const
export const ART_STYLE_PRESETS = ['wuxia', 'xianxia', 'anime', 'romance', 'realistic', 'ink wash', 'fantasy', 'horror'] as const

// Story UI language → RenderRequest.voice_language locale (backend routes TTS by
// this: vi→Gemini, en/ja→ElevenLabs via resolve_story_tts_engine).
export const VOICE_LOCALE: Record<StoryLang, 'vi-VN' | 'en-US' | 'ja-JP'> = {
  vi: 'vi-VN', en: 'en-US', ja: 'ja-JP',
}

export interface StoryConfig {
  language: StoryLang
  seriesId: string
  chapterNo: number
  artStyle: string
  ratio: Ratio
  readingPace: ReadingPace
  aiBudget: number
  subEnabled: boolean
  subStyle: string
  wordByWord: boolean
  outputDir: string
}

export const DEFAULT_STORY_CFG: StoryConfig = {
  language: 'vi', seriesId: '', chapterNo: 0, artStyle: '', ratio: 'r916',
  readingPace: 'normal', aiBudget: 0, subEnabled: true, subStyle: 'auto',
  // Story chapters are long — word-by-word (Whisper per shot) is off by default.
  wordByWord: false, outputDir: '',
}

// Client-side narration audit (mirror of the backend narration_audit) — shot cards.
export const _CPS = 15
export type AuditFlag = 'overloaded' | 'sparse' | 'ok' | 'none'
