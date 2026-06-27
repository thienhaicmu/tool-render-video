/**
 * render-profiles.test.ts — Pha 2 (Render Profiles) coverage.
 *
 * Pins the localStorage-backed profile module:
 *   - profileFromConfig strips machine/source-specific fields
 *   - the 3 built-ins are always present and flagged builtin
 *   - save persists (built-ins first, user profiles after)
 *   - the saved snapshot excludes outputDir & friends
 *   - delete removes a user profile and never touches built-ins
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  BUILTIN_PROFILES,
  listProfiles,
  saveProfile,
  deleteProfile,
  profileFromConfig,
} from '../src/features/clip-studio/render/profiles'
import type { ConfigState } from '../src/features/clip-studio/render/types'

const fullCfg: ConfigState = {
  ratio: 'r916', minSec: 30, maxSec: 60, trimIn: 0, trimOut: 0, style: 'slay_soft_01',
  platform: 'tiktok', aiMarket: 'us',
  multiVariant: false, ctaEnabled: false, ctaType: 'auto',
  hookApplyEnabled: false, hookOverlayEnabled: false, structureBias: null,
  clipLock: [{ start_sec: 1, end_sec: 2 }], clipExclude: [],
  subEnabled: true, subStyle: 'opus_pop', subHighlight: true, subFontSize: 0,
  subTranslate: false, subTranslateLang: 'en', subEmphasis: null,
  assetLogoPath: 'C:\\logo.png', assetIntroPath: null, assetOutroPath: null,
  whisperModel: 'auto',
  narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  voiceSource: 'translated_subtitle', voiceText: 'secret notes', voiceMixMode: 'replace_original',
  outputDir: 'D:\\out',
  renderProfile: 'balanced', targetDuration: 90, outputCount: 1, videoType: 'auto',
  hookStrength: 'balanced', focusMode: 'auto',
  llmEnabled: true, aiProvider: 'gemini', llmModel: '', llmLanguage: 'auto',
}

beforeEach(() => {
  localStorage.clear()
})

describe('Pha 2 — profileFromConfig', () => {
  it('strips machine/source-specific fields, keeps style choices', () => {
    const p = profileFromConfig(fullCfg)
    // Excluded
    expect(p.outputDir).toBeUndefined()
    expect(p.voiceText).toBeUndefined()
    expect(p.clipLock).toBeUndefined()
    expect(p.clipExclude).toBeUndefined()
    expect(p.assetLogoPath).toBeUndefined()
    // Kept
    expect(p.ratio).toBe('r916')
    expect(p.platform).toBe('tiktok')
    expect(p.subStyle).toBe('opus_pop')
    expect(p.videoType).toBe('auto')
  })
})

describe('Pha 2 — built-ins', () => {
  it('has 3 built-ins, all flagged builtin', () => {
    expect(BUILTIN_PROFILES).toHaveLength(3)
    expect(BUILTIN_PROFILES.every((p) => p.builtin === true)).toBe(true)
    expect(BUILTIN_PROFILES.map((p) => p.name)).toEqual(['TikTok', 'Reels', 'Shorts'])
  })

  it('listProfiles returns only built-ins when nothing is saved', () => {
    expect(listProfiles()).toHaveLength(3)
  })
})

describe('Pha 2 — save / delete', () => {
  it('persists a user profile after the built-ins, excluding outputDir', () => {
    const saved = saveProfile('My Vertical', fullCfg)
    const all = listProfiles()
    expect(all).toHaveLength(4)
    // Built-ins first, user profile last.
    expect(all.slice(0, 3).every((p) => p.builtin)).toBe(true)
    expect(all[3].id).toBe(saved.id)
    expect(all[3].name).toBe('My Vertical')
    expect(all[3].cfg.outputDir).toBeUndefined()
    expect(all[3].cfg.platform).toBe('tiktok')
  })

  it('survives a reload (reads back from localStorage)', () => {
    saveProfile('Persisted', fullCfg)
    // Fresh read — listProfiles re-parses localStorage each call.
    expect(listProfiles().some((p) => p.name === 'Persisted')).toBe(true)
  })

  it('delete removes a user profile but never the built-ins', () => {
    const saved = saveProfile('Temp', fullCfg)
    expect(listProfiles()).toHaveLength(4)
    deleteProfile(saved.id)
    const after = listProfiles()
    expect(after).toHaveLength(3)
    expect(after.every((p) => p.builtin)).toBe(true)
    // Deleting a built-in id is a no-op.
    deleteProfile('builtin-tiktok')
    expect(listProfiles()).toHaveLength(3)
  })

  it('blank name falls back to "Untitled"', () => {
    const saved = saveProfile('   ', fullCfg)
    expect(saved.name).toBe('Untitled')
  })
})
