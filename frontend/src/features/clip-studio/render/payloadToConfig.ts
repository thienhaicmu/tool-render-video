/**
 * payloadToConfig — P4.B: the inverse of buildRenderPayload.
 *
 * "Duplicate" from Library used to restore only ~6 of ~40 fields from the
 * stored payload_json — the user believed their settings were copied, but
 * subtitles/narration/LLM/trim all silently reset to defaults. This maps a
 * stored RenderRequest payload back onto ConfigState 1:1 with defensive
 * type checks (stored payloads may predate fields or hold nulls).
 *
 * Keep in lockstep with buildRenderPayload.ts — every field written there
 * should be read back here (round-trip).
 */
import type { ConfigState } from './types'

const RATIO_REVERSE: Record<string, ConfigState['ratio']> = {
  '9:16': 'r916', '3:4': 'r34', '4:5': 'r45', '1:1': 'r11', '16:9': 'r169',
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.length > 0 ? v : undefined
}
function num(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}
function bool(v: unknown): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined
}
function oneOf<T extends string>(v: unknown, allowed: readonly T[]): T | undefined {
  return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : undefined
}

export function payloadToConfig(payload: Record<string, unknown>): Partial<ConfigState> {
  const p = payload
  const patch: Partial<ConfigState> = {}

  // Frame / duration / counts
  const ratio = str(p.aspect_ratio)
  if (ratio && RATIO_REVERSE[ratio]) patch.ratio = RATIO_REVERSE[ratio]
  const minSec = num(p.min_part_sec)
  if (minSec !== undefined) patch.minSec = minSec
  const maxSec = num(p.max_part_sec)
  if (maxSec !== undefined) patch.maxSec = maxSec
  const trimIn = num(p.edit_trim_in)
  if (trimIn !== undefined) patch.trimIn = trimIn
  const trimOut = num(p.edit_trim_out)
  if (trimOut !== undefined) patch.trimOut = trimOut
  const dur = num(p.target_duration)
  if (dur !== undefined && dur > 0) patch.targetDuration = dur
  const outCount = num(p.output_count)
  if (outCount !== undefined && outCount >= 1) patch.outputCount = outCount

  // Platform / style / quality / mode
  const platform = oneOf(p.target_platform, ['tiktok', 'youtube_shorts', 'instagram_reels'] as const)
  if (platform) patch.platform = platform
  const style = str(p.effect_preset)
  if (style) patch.style = style
  const profile = oneOf(p.render_profile, ['fast', 'balanced', 'quality', 'best'] as const)
  if (profile) patch.renderProfile = profile
  const format = oneOf(p.render_format, ['clips', 'recap'] as const)
  if (format) patch.renderFormat = format
  const story = bool(p.use_story_intelligence)
  if (story !== undefined) patch.useStoryIntelligence = story
  const whisper = str(p.whisper_model)
  patch.whisperModel = (whisper ?? 'auto') as ConfigState['whisperModel']
  const reframe = oneOf(p.reframe_mode, ['auto', 'face', 'object', 'center'] as const)
  if (reframe) patch.focusMode = reframe

  // Subtitles
  const sub = bool(p.add_subtitle)
  if (sub !== undefined) patch.subEnabled = sub
  const subStyle = str(p.subtitle_style)
  if (subStyle) patch.subStyle = subStyle
  const hl = bool(p.highlight_per_word)
  if (hl !== undefined) patch.subHighlight = hl
  const fontSize = num(p.sub_font_size)
  if (fontSize !== undefined) patch.subFontSize = fontSize
  patch.subTranslate = p.subtitle_translate_enabled === true
  const subLang = oneOf(p.subtitle_target_language, ['vi', 'en', 'ja'] as const)
  if (subLang) patch.subTranslateLang = subLang

  // Narration cluster — payload omits these when voice is off, so absent
  // fields fall back to constructor defaults rather than stale values.
  const voice = bool(p.voice_enabled)
  patch.narrEnabled = voice === true
  const vSrc = oneOf(p.voice_source, ['subtitle', 'translated_subtitle', 'ai_rewrite', 'manual'] as const)
  if (vSrc) patch.voiceSource = vSrc
  const vText = str(p.voice_text)
  if (vText) patch.voiceText = vText
  if (typeof p.rewrite_tone === 'string') patch.rewriteTone = p.rewrite_tone
  const narrMode = oneOf(p.narration_mode, ['', 'reaction'] as const)
  if (narrMode !== undefined) patch.narrationMode = narrMode
  const intensity = oneOf(p.reaction_intensity, ['', 'low', 'medium', 'high'] as const)
  if (intensity !== undefined) patch.reactionIntensity = intensity
  const vLang = oneOf(p.voice_language, ['vi-VN', 'ja-JP', 'ko-KR', 'en-US', 'en-GB'] as const)
  if (vLang) patch.voiceLang = vLang
  const vGender = oneOf(p.voice_gender, ['female', 'male'] as const)
  if (vGender) patch.voiceGender = vGender
  const tts = oneOf(p.tts_engine, ['edge', 'xtts'] as const)
  if (tts) patch.ttsEngine = tts
  const mix = oneOf(p.voice_mix_mode, ['replace_original', 'keep_original_low'] as const)
  if (mix) patch.voiceMixMode = mix

  // LLM segment selection
  const llm = bool(p.llm_enabled)
  patch.llmEnabled = llm === true
  const provider = oneOf(p.ai_provider, ['gemini', 'openai', 'claude'] as const)
  if (provider) patch.aiProvider = provider
  const model = str(p.llm_model)
  if (model) patch.llmModel = model
  const llmLang = str(p.llm_language)
  patch.llmLanguage = llmLang ?? 'auto'

  // Extras
  patch.multiVariant = p.multi_variant === true
  patch.ctaEnabled = p.cta_enabled === true
  const cta = oneOf(p.cta_type, ['auto', 'comment', 'part_2', 'follow'] as const)
  if (cta) patch.ctaType = cta
  patch.hookApplyEnabled = p.hook_apply_enabled === true
  patch.hookOverlayEnabled = p.hook_overlay_enabled === true

  // Assets + output dir
  const logo = str(p.asset_logo_path)
  if (logo) patch.assetLogoPath = logo
  const intro = str(p.asset_intro_path)
  if (intro) patch.assetIntroPath = intro
  const outro = str(p.asset_outro_path)
  if (outro) patch.assetOutroPath = outro
  const outDir = str(p.output_dir)
  if (outDir && outDir !== 'output') patch.outputDir = outDir

  return patch
}
