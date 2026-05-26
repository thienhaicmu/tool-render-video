/**
 * render-validation.test.ts — pure logic tests for validateRenderForm, isFormValid, buildRenderPayload.
 * No rendering needed.
 */
import { describe, it, expect } from 'vitest'
import {
  validateRenderForm,
  isFormValid,
  buildRenderPayload,
} from '../src/features/render/RenderForm.schema'
import type { RenderFormState } from '../src/features/render/RenderForm.types'

const VALID_STATE: RenderFormState = {
  source_mode: 'youtube',
  youtube_url: 'https://www.youtube.com/watch?v=abc123',
  source_video_path: '',
  output_dir: 'D:\\renders\\test',
  target_platform: 'youtube_shorts',
  aspect_ratio: '3:4',
  subtitle_style: 'tiktok_bounce_v1',
  effect_preset: 'slay_soft_01',
  render_profile: 'quality',
  min_part_sec: 15,
  max_part_sec: 60,
  max_export_parts: 3,
  add_subtitle: true,
  ai_director_enabled: true,
  hook_overlay_enabled: true,
  remotion_hook_intro: true,
  title_overlay_text: '',
  playback_speed: 1.0,
  motion_aware_crop: false,
  reframe_mode: 'auto',
  frame_scale_x: 1.0,
  frame_scale_y: 1.0,
}

describe('validateRenderForm — output_dir', () => {
  it('empty output_dir → error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, output_dir: '' })
    expect(errors.output_dir).toBeTruthy()
  })

  it('whitespace-only output_dir → error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, output_dir: '   ' })
    expect(errors.output_dir).toBeTruthy()
  })

  it('valid output_dir → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, output_dir: 'D:\\renders' })
    expect(errors.output_dir).toBeUndefined()
  })
})

describe('validateRenderForm — source mode', () => {
  it('youtube mode + empty youtube_url → error', () => {
    const errors = validateRenderForm({
      ...VALID_STATE,
      source_mode: 'youtube',
      youtube_url: '',
    })
    expect(errors.youtube_url).toBeTruthy()
  })

  it('youtube mode + url without http → error', () => {
    const errors = validateRenderForm({
      ...VALID_STATE,
      source_mode: 'youtube',
      youtube_url: 'www.youtube.com/watch?v=abc',
    })
    expect(errors.youtube_url).toBeTruthy()
  })

  it('youtube mode + valid url → no error', () => {
    const errors = validateRenderForm({
      ...VALID_STATE,
      source_mode: 'youtube',
      youtube_url: 'https://youtube.com/watch?v=abc',
    })
    expect(errors.youtube_url).toBeUndefined()
  })

  it('local mode + empty source_video_path → error', () => {
    const errors = validateRenderForm({
      ...VALID_STATE,
      source_mode: 'local',
      source_video_path: '',
    })
    expect(errors.source_video_path).toBeTruthy()
  })

  it('local mode + valid path → no error', () => {
    const errors = validateRenderForm({
      ...VALID_STATE,
      source_mode: 'local',
      source_video_path: 'C:\\Videos\\test.mp4',
    })
    expect(errors.source_video_path).toBeUndefined()
  })
})

describe('validateRenderForm — part duration', () => {
  it('min_part_sec=4 → error (must be >= 5)', () => {
    const errors = validateRenderForm({ ...VALID_STATE, min_part_sec: 4 })
    expect(errors.min_part_sec).toBeTruthy()
  })

  it('min_part_sec=5 → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, min_part_sec: 5 })
    expect(errors.min_part_sec).toBeUndefined()
  })

  it('max_part_sec=301 → error (must be <= 300)', () => {
    const errors = validateRenderForm({ ...VALID_STATE, max_part_sec: 301 })
    expect(errors.max_part_sec).toBeTruthy()
  })

  it('max_part_sec=300 → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, max_part_sec: 300 })
    expect(errors.max_part_sec).toBeUndefined()
  })

  it('min=30, max=20 → error (min must be < max)', () => {
    const errors = validateRenderForm({ ...VALID_STATE, min_part_sec: 30, max_part_sec: 20 })
    expect(errors.min_part_sec).toBeTruthy()
  })

  it('min=30, max=30 → error (min must be < max, equal is invalid)', () => {
    const errors = validateRenderForm({ ...VALID_STATE, min_part_sec: 30, max_part_sec: 30 })
    expect(errors.min_part_sec).toBeTruthy()
  })
})

describe('validateRenderForm — max_export_parts', () => {
  it('max_export_parts=0 → error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, max_export_parts: 0 })
    expect(errors.max_export_parts).toBeTruthy()
  })

  it('max_export_parts=1 → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, max_export_parts: 1 })
    expect(errors.max_export_parts).toBeUndefined()
  })
})

describe('validateRenderForm — playback_speed', () => {
  it('playback_speed=0.4 → error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, playback_speed: 0.4 })
    expect(errors.playback_speed).toBeTruthy()
  })

  it('playback_speed=1.6 → error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, playback_speed: 1.6 })
    expect(errors.playback_speed).toBeTruthy()
  })

  it('playback_speed=0.5 → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, playback_speed: 0.5 })
    expect(errors.playback_speed).toBeUndefined()
  })

  it('playback_speed=1.5 → no error', () => {
    const errors = validateRenderForm({ ...VALID_STATE, playback_speed: 1.5 })
    expect(errors.playback_speed).toBeUndefined()
  })
})

describe('validateRenderForm — valid full state', () => {
  it('valid full state → no errors', () => {
    const errors = validateRenderForm(VALID_STATE)
    expect(Object.keys(errors)).toHaveLength(0)
  })
})

describe('isFormValid', () => {
  it('empty errors → true', () => {
    expect(isFormValid({})).toBe(true)
  })

  it('has any error → false', () => {
    expect(isFormValid({ output_dir: 'required' })).toBe(false)
  })

  it('has youtube_url error → false', () => {
    expect(isFormValid({ youtube_url: 'URL required' })).toBe(false)
  })
})

describe('buildRenderPayload', () => {
  it('maps formState to correct RenderRequest fields', () => {
    const payload = buildRenderPayload(VALID_STATE)
    expect(payload.source_mode).toBe('youtube')
    expect(payload.output_dir).toBe('D:\\renders\\test')
    expect(payload.target_platform).toBe('youtube_shorts')
    expect(payload.aspect_ratio).toBe('3:4')
    expect(payload.subtitle_style).toBe('tiktok_bounce_v1')
    expect(payload.effect_preset).toBe('slay_soft_01')
    expect(payload.render_profile).toBe('quality')
    expect(payload.min_part_sec).toBe(15)
    expect(payload.max_part_sec).toBe(60)
    expect(payload.max_export_parts).toBe(3)
    expect(payload.add_subtitle).toBe(true)
    expect(payload.ai_director_enabled).toBe(true)
    expect(payload.hook_overlay_enabled).toBe(true)
    expect(payload.remotion_hook_intro).toBe(true)
    expect(payload.playback_speed).toBe(1.0)
  })

  it('source_mode=youtube → sets youtube_url, NOT source_video_path', () => {
    const state: RenderFormState = {
      ...VALID_STATE,
      source_mode: 'youtube',
      youtube_url: 'https://youtube.com/watch?v=abc',
      source_video_path: 'C:\\video.mp4',
    }
    const payload = buildRenderPayload(state)
    expect(payload.youtube_url).toBe('https://youtube.com/watch?v=abc')
    expect(payload.source_video_path).toBeUndefined()
  })

  it('source_mode=local → sets source_video_path, NOT youtube_url', () => {
    const state: RenderFormState = {
      ...VALID_STATE,
      source_mode: 'local',
      youtube_url: 'https://youtube.com/watch?v=abc',
      source_video_path: 'C:\\video.mp4',
    }
    const payload = buildRenderPayload(state)
    expect(payload.source_video_path).toBe('C:\\video.mp4')
    expect(payload.youtube_url).toBeUndefined()
  })

  it('title_overlay_text empty → no title_overlay_text in payload', () => {
    const payload = buildRenderPayload({ ...VALID_STATE, title_overlay_text: '' })
    expect(payload.title_overlay_text).toBeUndefined()
    expect(payload.add_title_overlay).toBeUndefined()
  })

  it('title_overlay_text set → included in payload with add_title_overlay=true', () => {
    const payload = buildRenderPayload({ ...VALID_STATE, title_overlay_text: 'My Title' })
    expect(payload.title_overlay_text).toBe('My Title')
    expect(payload.add_title_overlay).toBe(true)
  })
})
