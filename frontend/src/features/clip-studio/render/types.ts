export type Step = 1 | 2 | 3 | 4
export type Ratio = 'r916' | 'r34' | 'r45' | 'r11' | 'r169'
export type CfgTab = 'ai' | 'sub' | 'narr' | 'output'

export interface Source { value: string }

export interface ConfigState {
  preset:        string
  ratio:         Ratio
  minSec:        number
  maxSec:        number
  clipCount:     number
  style:         string
  platform:      'tiktok' | 'youtube_shorts' | 'instagram_reels'
  aiMarket:      string
  aiEnabled:          boolean
  multiVariant:       boolean
  ctaEnabled:         boolean
  ctaType:            'auto' | 'comment' | 'part_2' | 'follow'
  hookApplyEnabled:   boolean
  hookOverlayEnabled: boolean
  structureBias:      'hook' | 'balanced' | 'story' | null
  clipLock:           Array<{ start_sec: number; end_sec: number }>
  clipExclude:        Array<{ start_sec: number; end_sec: number }>
  motionCrop:         boolean
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
  assetMusicProfile: 'clean' | 'energetic' | 'soft' | null
  whisperModel:      string
  partOrder:       'viral' | 'sequential'
  narrEnabled:   boolean
  voiceLang:     string
  voiceGender:   'female' | 'male'
  ttsEngine:     'edge' | 'xtts'
  voiceSource:   'subtitle' | 'translated_subtitle' | 'manual'
  voiceText:     string
  voiceMixMode:  'replace_original' | 'keep_original_low'
  outputDir:     string
  renderProfile: 'fast' | 'balanced' | 'quality' | 'best'
  targetDuration:  number
  outputCount:     number
  videoType:       'auto' | 'viral' | 'storytelling' | 'educational' | 'emotional' | 'high_retention'
  energyStyle:     'auto' | 'fast' | 'balanced' | 'slow'
  hookStrength:    'aggressive' | 'balanced' | 'soft'
  focusMode:       'auto' | 'face' | 'object' | 'center'
  outputLanguage:  string
  narrationStyle:  'auto' | 'energetic' | 'calm' | 'emotional'
  subDensity:      'auto' | 'low' | 'medium' | 'high'
  subLanguage:     string
  aiAnalysisMode:    'local' | 'cloud' | 'hybrid'
  aiCloudProvider:   'groq' | 'openai'
  aiCloudApiKey:     string
  aiCloudModel:      string
  aiContentDriven:   boolean
  // LLM segment selection (Phase I — multi-provider)
  groqEnabled:          boolean
  aiProvider:           'groq' | 'gemini'  // UI only exposes these two
  groqModel:            string             // also used as gemini model when aiProvider=gemini
  groqContentLanguage:  string
}

export type ClipSlot = {
  part_no: number
  status: string
  progress_percent: number
  duration?: number
  message?: string
}
