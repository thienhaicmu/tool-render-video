import { describe, it, expect } from 'vitest'
import { presetParamsToConfigPatch } from '../src/features/clip-studio/render/presetMapping'

describe('presetParamsToConfigPatch (F2)', () => {
  it('maps FE-facing snake_case preset params to ConfigState keys', () => {
    const patch = presetParamsToConfigPatch({
      output_count: 5,
      target_platform: 'tiktok',
      target_duration: 180,
      video_type: 'viral',
      hook_strength: 'aggressive',
      add_subtitle: true,
      subtitle_style: 'opus_pop',
      llm_enabled: true,
      ai_provider: 'gemini',
    })
    expect(patch).toEqual({
      outputCount: 5,
      platform: 'tiktok',
      targetDuration: 180,
      videoType: 'viral',
      hookStrength: 'aggressive',
      subEnabled: true,
      subStyle: 'opus_pop',
      llmEnabled: true,
      aiProvider: 'gemini',
    })
  })

  it('ignores BE-only params that have no ConfigState field', () => {
    // ai_clip_* are applied server-side, not reflected into the form.
    const patch = presetParamsToConfigPatch({
      ai_clip_min_duration_sec: 15,
      ai_clip_max_duration_sec: 60,
      output_count: 3,
    })
    expect(patch).toEqual({ outputCount: 3 })
  })

  it('skips null / undefined values', () => {
    const patch = presetParamsToConfigPatch({
      output_count: undefined as unknown as number,
      video_type: null as unknown as string,
      hook_strength: 'soft',
    })
    expect(patch).toEqual({ hookStrength: 'soft' })
  })

  it('returns empty patch for empty input', () => {
    expect(presetParamsToConfigPatch({})).toEqual({})
  })
})
