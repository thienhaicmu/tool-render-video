/**
 * API types derived from backend/app/models/schemas.py and docs/ui/UI_BACKEND_CONTRACT.md
 * Source of truth: Phase 5.10 contract freeze.
 */

// ── Text Layer sub-types ──────────────────────────────────────────────────────

export interface TextLayerOutline {
  enabled: boolean
  thickness: number
}

export interface TextLayerShadow {
  enabled: boolean
  offset_x: number
  offset_y: number
}

export interface TextLayerBackground {
  enabled: boolean
  color: string
  padding: number
}

export interface TextLayerConfig {
  id: string
  text: string
  font_family: string
  font_size: number
  color: string
  position: string
  x_percent?: number | null
  y_percent?: number | null
  alignment: string
  bold: boolean
  outline: TextLayerOutline
  shadow: TextLayerShadow
  background: TextLayerBackground
  start_time: number
  end_time: number
  order: number
}

// ── Clip lock / exclude (UP26) ────────────────────────────────────────────────

export interface TimeRange {
  start_sec: number
  end_sec: number
}

// ── RenderRequest ─────────────────────────────────────────────────────────────
// UI-facing fields only — DO NOT include INTERNAL_ONLY or DO_NOT_USE fields.
// See docs/ui/UI_BACKEND_CONTRACT.md §5 for full field status matrix.

export interface RenderRequest {
  // Source group
  source_mode: 'youtube' | 'local'
  source_quality_mode?: 'standard_1080' | 'high_1440' | 'best_available'
  youtube_url?: string
  youtube_urls?: string[]
  source_video_path?: string

  // Output group
  output_mode?: 'manual'
  output_dir: string
  render_output_subdir?: string
  keep_source_copy?: boolean
  cleanup_temp_files?: boolean

  // Profile / quality
  render_profile?: 'fast' | 'balanced' | 'quality' | 'best'
  output_fps?: number

  // Segmentation
  auto_detect_scene?: boolean
  min_part_sec?: number
  max_part_sec?: number
  max_export_parts?: number | null
  part_order?: 'viral' | 'sequential'

  // Subtitle
  add_subtitle?: boolean
  subtitle_style?: string
  highlight_per_word?: boolean
  sub_font_size?: number
  subtitle_translate_enabled?: boolean
  subtitle_target_language?: 'vi' | 'en' | 'ja'

  // Frame / crop
  aspect_ratio?: string

  // Overlay / effect
  add_title_overlay?: boolean
  title_overlay_text?: string
  effect_preset?: string
  remotion_hook_intro?: boolean

  // Reup mode
  reup_mode?: boolean
  reup_overlay_enable?: boolean
  reup_bgm_enable?: boolean
  reup_bgm_path?: string | null
  playback_speed?: number

  // Editor session (UI controls)
  edit_session_id?: string | null
  edit_trim_in?: number
  edit_trim_out?: number
  edit_volume?: number
  text_layers?: TextLayerConfig[]
  voice_enabled?: boolean
  voice_language?: 'vi-VN' | 'ja-JP' | 'en-US' | 'en-GB'
  voice_gender?: 'female' | 'male'
  voice_source?: 'manual' | 'subtitle' | 'translated_subtitle'
  voice_text?: string | null
  hook_apply_enabled?: boolean
  hook_overlay_enabled?: boolean

  // AI Director
  ai_director_enabled?: boolean
  target_platform?: 'tiktok' | 'youtube_shorts' | 'instagram_reels'
  multi_variant?: boolean
  cta_enabled?: boolean
  cta_type?: 'auto' | 'comment' | 'part_2' | 'follow'

  // Pro Timeline Steering (UP26)
  clip_lock?: TimeRange[] | null
  clip_exclude?: TimeRange[] | null
  structure_bias?: 'hook' | 'balanced' | 'story' | null
  subtitle_emphasis?: 'subtle' | 'balanced' | 'aggressive' | null

  // Creator Asset Intelligence (UP27)
  asset_logo_path?: string | null
  asset_intro_path?: string | null
  asset_outro_path?: string | null
  asset_music_profile?: 'clean' | 'energetic' | 'soft' | null
}

// ── RenderResponse ────────────────────────────────────────────────────────────

export interface RenderResponse {
  job_id: string
  status: string
  resume_mode?: boolean
}

// ── JobStatus (from GET /api/jobs/{job_id}) ───────────────────────────────────

export type JobStatusValue =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_errors'
  | 'failed'
  | 'interrupted'
  | 'cancelled'
  | 'cancelling'

export interface JobStatus {
  job_id: string
  kind: 'render' | 'render_batch' | 'download'
  status: JobStatusValue
  stage: string
  progress_percent: number
  message: string
  payload_json: string
  result_json: string
  created_at: string
  updated_at: string
}

// ── JobPart (from GET /api/jobs/{job_id}/parts) ───────────────────────────────

export type JobPartStatus =
  | 'done'
  | 'failed'
  | 'waiting'
  | 'cutting'
  | 'transcribing'
  | 'rendering'
  | 'downloading'
  | 'cancelled'

export interface JobPart {
  part_no: number
  status: JobPartStatus
  progress_percent: number
  output_file: string
  updated_at: string
}

// ── Quality types (from docs/ui/UI_BACKEND_CONTRACT.md §8) ───────────────────

export interface QualityIssue {
  code: string
  severity: 'critical' | 'error' | 'warning' | 'info'
  message: string
  confidence: number
  part_no: number
  evidence: Record<string, unknown>
  recommended_action: string
}

export interface QualityReport {
  job_id: string
  part_no: number
  score: number
  issues: QualityIssue[]
  metrics: Record<string, unknown>
  ai_trace_refs: string[]
  created_at: string
}

export interface QualityPartSummary {
  part_no: number
  available: boolean
  score: number
  issue_count: number
  critical_count: number
  error_count: number
  warning_count: number
  info_count: number
  report: QualityReport | null
}

export interface QualitySummaryAggregate {
  available_parts: number
  total_parts: number
  average_score: number
  critical_count: number
  error_count: number
  warning_count: number
  info_count: number
}

export interface QualitySummary {
  job_id: string
  parts: QualityPartSummary[]
  summary: QualitySummaryAggregate
}

// ── WebSocket event (from docs/ui/UI_BACKEND_CONTRACT.md §11) ─────────────────

export interface WsProgressSummary {
  total_parts: number
  completed_parts: number
  failed_parts: number
  pending_parts: number
  processing_parts: number
  in_progress_count: number
  active_parts: Array<{ part_no: number; status: string; progress_percent: number }>
  stuck_parts: Array<{ part_no: number; status: string; stuck_seconds: number }>
  current_part: number | null
  current_stage: string | null
  overall_progress_percent: number
  parts_percent: number
}

export interface WebSocketEvent {
  job: JobStatus
  parts: JobPart[]
  summary: WsProgressSummary
}

export interface WebSocketErrorEvent {
  error: 'not_found' | string
}

// ── File upload ───────────────────────────────────────────────────────────────

export interface UploadFileResponse {
  path: string
}

// ── History ───────────────────────────────────────────────────────────────────

export interface HistoryItem {
  job_id: string
  kind: 'render' | 'download'
  status: string
  stage: string
  title: string
  source_hint: string | null
  timestamp: string
  created_at: string
  updated_at: string
  output_dir: string | null
  completed_count: number
  failed_count: number
  unsupported_count: number
  total_count: number
  summary_text: string
  can_open_folder: boolean
  can_retry: boolean
  can_rerun: boolean
}

export interface JobsHistoryResponse {
  items: HistoryItem[]
  limit: number
  offset: number
  has_more: boolean
}

// ── Queue status ──────────────────────────────────────────────────────────────

export interface QueueStatus {
  max_concurrent: number
  active: number
  pending: number
  available_slots: number
}
