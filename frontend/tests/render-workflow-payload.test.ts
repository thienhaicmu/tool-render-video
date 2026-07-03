/**
 * Wire-payload regression guard (Audit 2026-06-08 T1.4 + follow-ups).
 *
 * T1.4 stripped a set of dead intent fields from the wire surface. This guard
 * pins that they never reappear as payload keys, and that the surviving live
 * fields stay on the wire.
 *
 * Rewritten (god-file decomposition, 2026-07): the payload is now built by the
 * extracted pure `buildRenderPayload(cfg, src)` (RenderWorkflow just calls it),
 * so this test invokes it directly and inspects Object.keys() — far more robust
 * than the previous source-text scrape of a `function buildPayloadForSource`
 * that no longer exists. The BE-side guard
 * `backend/tests/test_render_request_public_no_dead_fields.py` is complementary.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { buildRenderPayload } from '../src/features/clip-studio/render/buildRenderPayload'
import type { ConfigState } from '../src/features/clip-studio/render/types'

// A complete, valid ConfigState (needs a real ratio so RATIO_INFO resolves).
function makeCfg(over: Partial<ConfigState> = {}): ConfigState {
  return {
    ratio: 'r916', minSec: 30, maxSec: 60, trimIn: 0, trimOut: 0,
    style: 'slay_soft_01', platform: 'tiktok',
    multiVariant: false, ctaEnabled: false, ctaType: 'auto',
    hookApplyEnabled: false, hookOverlayEnabled: false,
    clipLock: [], clipExclude: [],
    subEnabled: true, subStyle: 'opus_pop',
    subHighlight: true, subFontSize: 0, subTranslate: false, subTranslateLang: 'en',
    assetLogoPath: null, assetIntroPath: null, assetOutroPath: null,
    whisperModel: 'auto',
    narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
    voiceSource: 'translated_subtitle', voiceText: '', rewriteTone: '', narrationMode: '',
    reactionIntensity: '', voiceMixMode: 'replace_original',
    outputDir: 'D:\\out',
    renderProfile: 'balanced', renderFormat: 'clips', useStoryIntelligence: false,
    targetDuration: 90, outputCount: 1, focusMode: 'auto',
    llmEnabled: true, aiProvider: 'gemini', llmModel: '', llmLanguage: 'auto',
    ...over,
  }
}

const payloadKeys = (over: Partial<ConfigState> = {}): string[] =>
  Object.keys(buildRenderPayload(makeCfg(over), 'C:\\video.mp4'))

const STRIPPED_FIELDS_PHASE_G = [
  'ai_director_enabled', 'ai_auto_cut', 'ai_use_semantic_hooks',
  'ai_render_influence_enabled', 'ai_beat_pulse_enabled',
  'ai_cloud_enabled', 'ai_cloud_provider', 'ai_cloud_api_key',
  'ai_cloud_model', 'ai_analysis_mode', 'ai_content_driven_selection',
]
const STRIPPED_FIELDS_UP26: string[] = []
const STRIPPED_FIELDS_UP27 = ['asset_music_profile']
const STRIPPED_FIELDS_V2 = ['energy_style', 'output_language', 'narration_style']
const STRIPPED_FIELDS_FOLLOWUP = ['max_export_parts', 'part_order']

const ALL_STRIPPED = [
  ...STRIPPED_FIELDS_PHASE_G,
  ...STRIPPED_FIELDS_UP26,
  ...STRIPPED_FIELDS_UP27,
  ...STRIPPED_FIELDS_V2,
  ...STRIPPED_FIELDS_FOLLOWUP,
]

describe('buildRenderPayload omits dead fields', () => {
  it.each(ALL_STRIPPED)('never includes %s as a payload key', (field) => {
    expect(payloadKeys()).not.toContain(field)
  })

  it('still sends target_duration (T2.4 wired it to the LLM)', () => {
    expect(payloadKeys()).toContain('target_duration')
  })

  it('still sends the live intent fields the engine consumes', () => {
    const keys = payloadKeys()
    expect(keys).toContain('target_platform')
    expect(keys).toContain('output_count')
    expect(keys).toContain('min_part_sec')
    expect(keys).toContain('max_part_sec')
  })

  it('does NOT send removed creator-preference fields (UI cleanup)', () => {
    const keys = payloadKeys()
    for (const f of ['hook_strength', 'video_type', 'ai_target_market', 'structure_bias', 'subtitle_emphasis', 'render_preset_id']) {
      expect(keys).not.toContain(f)
    }
  })

  it('sends edit_trim_in / edit_trim_out (Pha 5.7 source trim)', () => {
    const keys = payloadKeys()
    expect(keys).toContain('edit_trim_in')
    expect(keys).toContain('edit_trim_out')
  })

  it('forces output_count to 1 in recap mode', () => {
    expect(buildRenderPayload(makeCfg({ renderFormat: 'recap', outputCount: 5 }), 'C:\\v.mp4').output_count).toBe(1)
  })
})

// The RenderRequest TS interface must also not declare the dead fields.
const API_TYPES_PATH = join(__dirname, '..', 'src', 'types', 'api.ts')

describe('`RenderRequest` TS interface omits dead fields', () => {
  it.each(ALL_STRIPPED)('never declares %s as an interface property', (field) => {
    const source = readFileSync(API_TYPES_PATH, 'utf-8')
    const startIdx = source.indexOf('export interface RenderRequest {')
    expect(startIdx).toBeGreaterThan(-1)
    let depth = 0
    let i = source.indexOf('{', startIdx)
    let endIdx = -1
    for (; i < source.length; i++) {
      const ch = source[i]
      if (ch === '{') depth++
      else if (ch === '}') { depth--; if (depth === 0) { endIdx = i; break } }
    }
    expect(endIdx).toBeGreaterThan(startIdx)
    const codeOnly = source.slice(startIdx, endIdx + 1)
      .split('\n')
      .map((line) => { const s = line.indexOf('//'); return s === -1 ? line : line.slice(0, s) })
      .join('\n')
    expect(codeOnly).not.toMatch(new RegExp(`(^|\\s|,|;)${field}\\s*\\?\\s*:`))
  })
})
