/**
 * useRenderConfig — Configure-state ownership extracted from RenderWorkflow
 * (god-file slice 2). Owns the cfg defaults, localStorage draft persistence,
 * the one-shot server-defaults hydration, and the setCfgKey/applyPreset
 * mutators. Behaviour is verbatim from the original component.
 */
import { useState, useEffect, useRef, type Dispatch, type SetStateAction } from 'react'
import type { ConfigState } from './types'
import { getRenderDefaults } from '@/api/renderDefaults'
import { PRESETS } from './constants'

const CFG_DRAFT_KEY = 'rw_cfg_draft_v1'

export interface RenderConfigApi {
  cfg: ConfigState
  setCfg: Dispatch<SetStateAction<ConfigState>>
  setCfgKey: <K extends keyof ConfigState>(k: K, v: ConfigState[K]) => void
  setRenderMode: (mode: ConfigState['renderFormat']) => void
  applyPreset: (id: string) => void
}

// Mode-appropriate baseline. Picking a mode applies these deterministically
// (per-mode defaults, NOT restored user behaviour). Explicit tweaks after the
// switch still win until the mode is switched again.
const MODE_DEFAULTS: Record<ConfigState['renderFormat'], Partial<ConfigState>> = {
  // Short vertical clips.
  clips: { ratio: 'r916' },
  // Long-form act-structured recap: landscape by default, narration-driven.
  recap: { ratio: 'r169', narrEnabled: true },
}

export function useRenderConfig(): RenderConfigApi {
  // P4.C — the Configure draft survives reloads. Only ai_provider used to
  // persist; a reload threw away everything else the user had dialed in.
  const hadDraftRef = useRef(false)
  const cfgDefaults: ConfigState = {
    ratio: 'r916', minSec: 30, maxSec: 60, trimIn: 0, trimOut: 0,
    style: 'slay_soft_01', platform: 'tiktok',
    multiVariant: false, ctaEnabled: false, ctaType: 'auto',
    hookApplyEnabled: false, hookOverlayEnabled: false,
    clipLock: [], clipExclude: [],
    subEnabled: true, subStyle: 'opus_pop',
    subHighlight: true, subFontSize: 0, subTranslate: false, subTranslateLang: 'en',
    assetLogoPath: null, assetIntroPath: null, assetOutroPath: null,
    whisperModel: 'auto',
    narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'gemini',
    voiceSource: 'translated_subtitle', voiceText: '', rewriteTone: '', narrationMode: '', reactionIntensity: '', voiceMixMode: 'replace_original',
    outputDir: '',
    renderProfile: 'balanced',
    renderFormat: 'clips',
    useStoryIntelligence: false,
    targetDuration: 90, outputCount: 1, focusMode: 'auto',
    llmEnabled:   true,
    aiProvider:   (localStorage.getItem('rw_ai_provider') as 'gemini' | 'openai' | 'claude') ?? 'gemini',
    llmModel:     '',
    llmLanguage:  'auto',
  }
  const [cfg, setCfg] = useState<ConfigState>(() => {
    try {
      const raw = localStorage.getItem(CFG_DRAFT_KEY)
      if (raw) {
        hadDraftRef.current = true
        const draft = JSON.parse(raw) as Partial<ConfigState>
        // Mode is NOT restored from prior behaviour — each session starts at
        // the default mode with that mode's baseline (per requirement: default
        // per mode, not per user behaviour). Everything else still persists.
        return {
          ...cfgDefaults, ...draft,
          renderFormat: cfgDefaults.renderFormat,
          ...MODE_DEFAULTS[cfgDefaults.renderFormat],
        }
      }
    } catch { /* corrupt draft — fall back to defaults */ }
    return cfgDefaults
  })

  // Debounced draft save.
  useEffect(() => {
    const id = setTimeout(() => {
      try { localStorage.setItem(CFG_DRAFT_KEY, JSON.stringify(cfg)) } catch { /* ignore */ }
    }, 800)
    return () => clearTimeout(id)
  }, [cfg])

  // S2.4 — auto-fill cfg from server-side render defaults on mount.
  // Fields only patch in if the server has them; null defaults stay
  // untouched so existing locally-stored choices (e.g. localStorage
  // ai_provider) still win when the user hasn't configured Settings.
  // Runs once — user edits to cfg after mount are NOT overwritten.
  useEffect(() => {
    let cancelled = false
    // P4.C — a restored draft is the user's explicit prior state; don't let
    // server-side defaults overwrite it on mount.
    if (hadDraftRef.current) return
    ;(async () => {
      try {
        const env = await getRenderDefaults()
        if (cancelled || !env.is_configured) return
        const d = env.render_defaults
        // Reverse-map "9:16" → "r916" etc. Skip when null or unknown.
        const ratioReverseMap: Record<string, ConfigState['ratio']> = {
          '9:16': 'r916', '3:4': 'r34', '4:5': 'r45',
          '1:1':  'r11',  '16:9': 'r169',
        }
        setCfg((prev) => {
          const patch: Partial<ConfigState> = {}
          if (d.aspect_ratio && ratioReverseMap[d.aspect_ratio]) {
            patch.ratio = ratioReverseMap[d.aspect_ratio]
          }
          if (d.subtitle_style) patch.subStyle = d.subtitle_style
          // voice_provider only patches when it matches one of the
          // engines cfg.ttsEngine accepts (edge | xtts | gemini).
          // 'elevenlabs' is a valid backend default but no FE field maps yet.
          if (d.voice_provider === 'edge' || d.voice_provider === 'xtts' || d.voice_provider === 'gemini') {
            patch.ttsEngine = d.voice_provider
          }
          if (
            d.llm_provider === 'gemini' ||
            d.llm_provider === 'openai' ||
            d.llm_provider === 'claude'
          ) {
            patch.aiProvider = d.llm_provider
          }
          // Preset = bundle of platform + style + ratio. Apply via
          // applyPreset semantics: look up PRESET entry, patch platform
          // + ratio. The user can still override after mount.
          if (d.preset) {
            const presetEntry = PRESETS.find((p) => p.id === d.preset)
            if (presetEntry) {
              patch.platform = presetEntry.platform
            }
          }
          return Object.keys(patch).length ? { ...prev, ...patch } : prev
        })
      } catch {
        // Defaults endpoint failure must never block the render flow.
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function setCfgKey<K extends keyof ConfigState>(k: K, v: ConfigState[K]) {
    if (k === 'aiProvider')      localStorage.setItem('rw_ai_provider', v as string)
    setCfg((p) => ({ ...p, [k]: v }))
  }
  function applyPreset(id: string) {
    const p = PRESETS.find((x) => x.id === id)
    if (!p) return
    setCfg((prev) => ({ ...prev, platform: p.platform, ratio: 'r916' }))
  }
  // Switching mode applies that mode's baseline defaults (deterministic).
  function setRenderMode(mode: ConfigState['renderFormat']) {
    setCfg((prev) => ({ ...prev, renderFormat: mode, ...MODE_DEFAULTS[mode] }))
  }

  return { cfg, setCfg, setCfgKey, setRenderMode, applyPreset }
}
