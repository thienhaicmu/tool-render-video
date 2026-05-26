/**
 * RenderForm types — form state and validation error shapes.
 */

export interface RenderFormState {
  source_mode: 'youtube' | 'local'
  youtube_url: string
  source_video_path: string
  output_dir: string
  target_platform: string
  aspect_ratio: string
  subtitle_style: string
  effect_preset: string
  render_profile: string
  min_part_sec: number
  max_part_sec: number
  max_export_parts: number
  add_subtitle: boolean
  ai_director_enabled: boolean
  hook_overlay_enabled: boolean
  remotion_hook_intro: boolean
  title_overlay_text: string
  playback_speed: number
  // Frame & Motion
  motion_aware_crop: boolean
  reframe_mode: string
  frame_scale_x: number
  frame_scale_y: number
  // AI market targeting
  ai_target_market: string
}

export interface RenderFormErrors {
  output_dir?: string
  youtube_url?: string
  source_video_path?: string
  min_part_sec?: string
  max_part_sec?: string
  max_export_parts?: string
  playback_speed?: string
}
