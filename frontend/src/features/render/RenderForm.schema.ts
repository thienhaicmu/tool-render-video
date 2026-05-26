/**
 * RenderForm validation schema — pure functions, no library.
 */
import type { RenderRequest } from '../../types/api'
import type { RenderFormState, RenderFormErrors } from './RenderForm.types'
import {
  PLATFORMS,
  ASPECT_RATIOS,
  SUBTITLE_STYLES,
  EFFECT_PRESETS,
  RENDER_PROFILES,
} from '../../lib/constants'

const PLATFORM_VALUES = PLATFORMS.map((p) => p.value)
const ASPECT_RATIO_VALUES = ASPECT_RATIOS.map((a) => a.value)
const SUBTITLE_STYLE_VALUES = SUBTITLE_STYLES.map((s) => s.value)
const EFFECT_PRESET_VALUES = EFFECT_PRESETS.map((e) => e.value)
const RENDER_PROFILE_VALUES = RENDER_PROFILES.map((r) => r.value)

export function validateRenderForm(state: RenderFormState): RenderFormErrors {
  const errors: RenderFormErrors = {}

  // output_dir: required
  if (!state.output_dir || state.output_dir.trim() === '') {
    errors.output_dir = 'Output directory is required'
  }

  // Source mode validation
  if (state.source_mode === 'youtube') {
    if (!state.youtube_url || state.youtube_url.trim() === '') {
      errors.youtube_url = 'YouTube URL is required'
    } else if (!state.youtube_url.trim().startsWith('http')) {
      errors.youtube_url = 'YouTube URL must start with http'
    }
  } else if (state.source_mode === 'local') {
    if (!state.source_video_path || state.source_video_path.trim() === '') {
      errors.source_video_path = 'Source video path is required'
    }
  }

  // min_part_sec: must be >= 5
  if (state.min_part_sec < 5) {
    errors.min_part_sec = 'Minimum part duration must be at least 5 seconds'
  }

  // max_part_sec: must be <= 300
  if (state.max_part_sec > 300) {
    errors.max_part_sec = 'Maximum part duration must be at most 300 seconds'
  }

  // min_part_sec must be < max_part_sec
  if (state.min_part_sec >= state.max_part_sec && !errors.min_part_sec && !errors.max_part_sec) {
    errors.min_part_sec = 'Minimum must be less than maximum part duration'
  }

  // max_export_parts: must be >= 1
  if (state.max_export_parts < 1) {
    errors.max_export_parts = 'Must export at least 1 part'
  }

  // playback_speed: must be >= 0.5 and <= 1.5
  if (state.playback_speed < 0.5 || state.playback_speed > 1.5) {
    errors.playback_speed = 'Playback speed must be between 0.5 and 1.5'
  }

  // Enum validation (silently ignore if unknown — fallback to default)
  // We validate but don't block — these come from controlled select elements

  return errors
}

export function isFormValid(errors: RenderFormErrors): boolean {
  return Object.keys(errors).length === 0
}

export function buildRenderPayload(state: RenderFormState): RenderRequest {
  const payload: RenderRequest = {
    source_mode: state.source_mode,
    output_dir: state.output_dir,
    target_platform: state.target_platform as RenderRequest['target_platform'],
    aspect_ratio: state.aspect_ratio,
    subtitle_style: state.subtitle_style,
    effect_preset: state.effect_preset,
    render_profile: state.render_profile as RenderRequest['render_profile'],
    min_part_sec: state.min_part_sec,
    max_part_sec: state.max_part_sec,
    max_export_parts: state.max_export_parts,
    add_subtitle: state.add_subtitle,
    ai_director_enabled: state.ai_director_enabled,
    hook_overlay_enabled: state.hook_overlay_enabled,
    remotion_hook_intro: state.remotion_hook_intro,
    playback_speed: state.playback_speed,
  }

  if (state.source_mode === 'youtube') {
    payload.youtube_url = state.youtube_url
  } else {
    payload.source_video_path = state.source_video_path
  }

  if (state.title_overlay_text && state.title_overlay_text.trim() !== '') {
    payload.title_overlay_text = state.title_overlay_text
    payload.add_title_overlay = true
  }

  payload.motion_aware_crop = state.motion_aware_crop
  payload.reframe_mode = state.reframe_mode
  payload.frame_scale_x = state.frame_scale_x
  payload.frame_scale_y = state.frame_scale_y

  return payload
}

// Re-export for use in tests
export { PLATFORM_VALUES, ASPECT_RATIO_VALUES, SUBTITLE_STYLE_VALUES, EFFECT_PRESET_VALUES, RENDER_PROFILE_VALUES }
