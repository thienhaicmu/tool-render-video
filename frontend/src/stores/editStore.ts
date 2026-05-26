import { create } from 'zustand'

export type TargetPlatform = 'tiktok' | 'youtube_shorts' | 'instagram_reels'
export type RenderProfile = 'fast' | 'balanced' | 'quality' | 'best'
export type PartOrder = 'viral' | 'sequential'

export interface ClipRange {
  start_sec: number
  end_sec: number
}

export interface EditSettings {
  targetPlatform: TargetPlatform
  aspectRatio: string
  selectedFormats: string[]
  outputFps: 30 | 60
  renderProfile: RenderProfile

  aiDirectorEnabled: boolean
  maxExportParts: number
  minPartSec: number
  maxPartSec: number
  partOrder: PartOrder

  addSubtitle: boolean
  subtitleStyle: string
  subFontSize: number
  highlightPerWord: boolean

  voiceEnabled: boolean
  voiceLanguage: 'vi-VN' | 'ja-JP' | 'en-US' | 'en-GB'
  voiceGender: 'female' | 'male'

  motionAwareCrop: boolean
  reframeMode: string

  clipLock: ClipRange[] | null
}

const PLATFORM_PRESETS: Record<TargetPlatform, Pick<EditSettings, 'aspectRatio' | 'outputFps'>> = {
  tiktok:            { aspectRatio: '9:16', outputFps: 30 },
  youtube_shorts:    { aspectRatio: '9:16', outputFps: 60 },
  instagram_reels:   { aspectRatio: '9:16', outputFps: 30 },
}

export const DEFAULT_EDIT_SETTINGS: EditSettings = {
  targetPlatform:    'tiktok',
  aspectRatio:       '9:16',
  selectedFormats:   ['9:16'],
  outputFps:         30,
  renderProfile:     'balanced',

  aiDirectorEnabled: true,
  maxExportParts:    3,
  minPartSec:        30,
  maxPartSec:        90,
  partOrder:         'viral',

  addSubtitle:       true,
  subtitleStyle:     'tiktok_bounce_v1',
  subFontSize:       28,
  highlightPerWord:  true,

  voiceEnabled:      false,
  voiceLanguage:     'en-US',
  voiceGender:       'female',

  motionAwareCrop:   false,
  reframeMode:       'subject',

  clipLock:          null,
}

interface EditStore {
  settings: EditSettings
  update: (patch: Partial<EditSettings>) => void
  setPlatform: (platform: TargetPlatform) => void
  toggleFormat: (ratio: string) => void
  addClipLock: (range: ClipRange) => void
  removeClipLock: (index: number) => void
  clearClipLock: () => void
  reset: () => void
}

export const useEditStore = create<EditStore>((set) => ({
  settings: { ...DEFAULT_EDIT_SETTINGS },

  update: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),

  setPlatform: (platform) =>
    set((s) => ({
      settings: {
        ...s.settings,
        targetPlatform: platform,
        ...PLATFORM_PRESETS[platform],
      },
    })),

  toggleFormat: (ratio) =>
    set((s) => {
      const current = s.settings.selectedFormats
      const hasIt = current.includes(ratio)
      const next = hasIt
        ? current.length > 1 ? current.filter((r) => r !== ratio) : current
        : [...current, ratio]
      return {
        settings: {
          ...s.settings,
          selectedFormats: next,
          aspectRatio: next[0] ?? '9:16',
        },
      }
    }),

  addClipLock: (range) =>
    set((s) => ({
      settings: {
        ...s.settings,
        clipLock: [...(s.settings.clipLock ?? []), range],
      },
    })),

  removeClipLock: (index) =>
    set((s) => ({
      settings: {
        ...s.settings,
        clipLock: s.settings.clipLock?.filter((_, i) => i !== index) ?? null,
      },
    })),

  clearClipLock: () => set((s) => ({ settings: { ...s.settings, clipLock: null } })),

  reset: () => set({ settings: { ...DEFAULT_EDIT_SETTINGS } }),
}))
