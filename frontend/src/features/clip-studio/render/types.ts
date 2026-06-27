export type Step = 1 | 2 | 3 | 4
export type Ratio = 'r916' | 'r34' | 'r45' | 'r11' | 'r169'
export type CfgTab = 'ai' | 'sub' | 'narr' | 'output'

export interface Source { value: string }

export interface ConfigState {
  ratio:         Ratio
  minSec:        number
  maxSec:        number
  // Pha 5.7 — source trim (seconds). 0 = no trim (whole source). Sent as
  // edit_trim_in / edit_trim_out (already wire-supported + pipeline-consumed).
  trimIn:        number
  trimOut:       number
  style:         string
  platform:      'tiktok' | 'youtube_shorts' | 'instagram_reels'
  aiMarket:      string
  multiVariant:       boolean
  ctaEnabled:         boolean
  ctaType:            'auto' | 'comment' | 'part_2' | 'follow'
  hookApplyEnabled:   boolean
  hookOverlayEnabled: boolean
  structureBias:      'hook' | 'balanced' | 'story' | null
  clipLock:           Array<{ start_sec: number; end_sec: number }>
  clipExclude:        Array<{ start_sec: number; end_sec: number }>
  subEnabled:       boolean
  subStyle:         string
  subHighlight:     boolean
  subFontSize:      number
  subTranslate:     boolean
  subTranslateLang: 'vi' | 'en' | 'ja'
  subEmphasis:      'subtle' | 'balanced' | 'aggressive' | null
  assetLogoPath:     string | null
  assetIntroPath:    string | null
  assetOutroPath:    string | null
  whisperModel:      string
  narrEnabled:   boolean
  voiceLang:     string
  voiceGender:   'female' | 'male'
  ttsEngine:     'edge' | 'xtts'
  voiceSource:   'subtitle' | 'translated_subtitle' | 'manual' | 'ai_rewrite'
  voiceText:     string
  rewriteTone:   string
  voiceMixMode:  'replace_original' | 'keep_original_low'
  outputDir:     string
  renderProfile: 'fast' | 'balanced' | 'quality' | 'best'
  // F2 — selected built-in preset id ('' = custom/none). Sent as
  // render_preset_id; the server fills BE-only preset params the FE can't
  // (ai_clip_*), the FE reflects the FE-facing ones into the form above.
  renderPresetId: string
  targetDuration:  number
  outputCount:     number
  videoType:       'auto' | 'viral' | 'storytelling' | 'educational' | 'emotional' | 'high_retention'
  hookStrength:    'aggressive' | 'balanced' | 'soft'
  focusMode:       'auto' | 'face' | 'object' | 'center'
  // LLM segment selection — multi-provider
  llmEnabled:          boolean
  aiProvider:          'gemini' | 'openai' | 'claude'
  llmModel:            string
  llmLanguage:         string
}

export type ClipSlot = {
  part_no: number
  status: string
  progress_percent: number
  duration?: number
  message?: string
}
