/**
 * types.ts — shared types + constants for the Content Studio (CM-9 split).
 *
 * Extracted verbatim from the former single-file ContentStudio.tsx so the phase
 * components (ScriptPhase / ReviewPhase / SceneRow / ContentMonitor) and the
 * shared presentational bits can import them without a circular dependency.
 */
import type { Ratio } from '../clip-studio/render/types'

export type BgKind = 'color' | 'image' | 'video'
export type ImagenTier = 'fast' | 'standard' | 'ultra'
export type Phase = 'script' | 'review'

export const RATIOS: Ratio[] = ['r916', 'r11', 'r169']
export const VOICE_LANGS = ['vi-VN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR'] as const
export const TTS_ENGINES = ['edge', 'xtts', 'gemini'] as const
// Real CapCut preset ids (ass_capcut.CAPCUT_PRESETS) + 'auto' = let the AI plan
// pick the style. Every option resolves to a distinct, valid style now (P1.1).
export const SUB_STYLES = ['auto', 'opus_pop', 'capcut_box', 'punch_green', 'karaoke_clean', 'smooth_premiere'] as const
export const EMOTIONS = ['normal', 'excited', 'calm', 'suspense', 'epic', 'sad', 'happy', 'curious', 'motivating', 'surprise'] as const

export interface Config {
  ratio: Ratio
  targetDuration: number
  bgKind: BgKind
  bgColor: string
  bgAssetPath: string
  voiceLang: typeof VOICE_LANGS[number]
  voiceGender: 'female' | 'male'
  ttsEngine: typeof TTS_ENGINES[number]
  subEnabled: boolean
  subStyle: string
  wordByWord: boolean
  bgmPath: string
  visualProvider: 'local' | 'stock' | 'ai_image' | 'ai_video' | 'ai_image_free'
  imagenTier: ImagenTier
  aiBudget: number
  outputDir: string
  tone: string
}

export const DEFAULT_CFG: Config = {
  ratio: 'r916', targetDuration: 90, bgKind: 'color', bgColor: '#101820', bgAssetPath: '',
  voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  subEnabled: true, subStyle: 'auto', wordByWord: true,
  bgmPath: '', visualProvider: 'local', imagenTier: 'standard', aiBudget: 0, outputDir: '', tone: '',
}

export interface VoiceCfg { lang: string; gender: 'female' | 'male'; engine: string }
export interface VisualCfg { provider: string; aspectApi: string; style: string; imagenTier: string }

export interface SceneMeta {
  n: number; role?: string; narration?: string; scene_title?: string
  // Rich per-scene fields carried on the content.plan.ready WS event context
  // (mirror of content_pipeline.py's scene projection) so the live monitor can
  // render emotion / pacing / visual / duration chips without the plan prop.
  emotion?: string; reading_speed?: number; visual_hint?: string
  est_duration_sec?: number; transition_hint?: string; visual_source?: string
}

// Client-side narration audit (mirror of the backend narration_audit) — shared by
// SceneRow badges + the AiInsights summary. Same thresholds as
// ContentPlan.narration_audit (chars vs capacity at ~15 chars/sec × speed).
export const _CPS = 15
export type AuditFlag = 'overloaded' | 'sparse' | 'ok' | 'none'

export const _PROVIDER_LABELS: Record<string, string> = {
  local: 'Local', stock: 'Stock', ai_image_free: 'Pollinations', ai_image: 'Imagen', ai_video: 'Veo',
}
