/**
 * API types — the curated, human-readable surface that frontend code
 * imports from. Hand-maintained to stay readable (with comments,
 * intentional Optional/never fields, etc.).
 *
 * Source of truth for runtime: backend/app/models/schemas.py.
 * Drift detection: openapi-generated.ts (auto-generated, see Sprint 5.1).
 * The CI "openapi-drift" job fails if the generated file diverges from
 * what `npm run gen:openapi` produces against the current FastAPI app.
 *
 * When adding or renaming a backend field:
 *   1. Edit schemas.py.
 *   2. Run `npm run gen:openapi` — regenerates openapi-generated.ts.
 *   3. Update this file to expose the new field (or rename), keeping the
 *      curated style.
 *   4. Commit both files together.
 *
 * Historical reference: Phase 5.10 contract freeze.
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
  source_mode: 'local'
  source_quality_mode?: 'standard_1080' | 'high_1440' | 'best_available'
  youtube_url?: string
  source_video_path?: string

  // Output group
  output_dir: string
  render_output_subdir?: string
  keep_source_copy?: boolean
  cleanup_temp_files?: boolean

  // Profile / quality
  render_profile?: 'fast' | 'balanced' | 'quality' | 'best'
  output_fps?: number
  whisper_model?: string

  // Segmentation
  auto_detect_scene?: boolean
  min_part_sec?: number
  max_part_sec?: number
  // T1.4 follow-up — Audit 2026-06-08: removed `max_export_parts` and
  // `part_order` from the wire surface. Both were sent by buildPayload
  // but the render engine reads neither — see render_public.py for
  // the per-field rationale. Kept in backend RenderRequest for
  // Sacred Contract #2 replay safety.

  // Subtitle
  add_subtitle?: boolean
  subtitle_style?: string
  highlight_per_word?: boolean
  sub_font_size?: number
  subtitle_translate_enabled?: boolean
  subtitle_target_language?: 'vi' | 'en' | 'ja'

  // Frame / crop
  aspect_ratio?: string
  motion_aware_crop?: boolean
  reframe_mode?: string
  frame_scale_x?: number
  frame_scale_y?: number

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

  // Asset Library — Phase C
  asset_id?: string | null

  // Editor session (UI controls)
  edit_session_id?: string | null
  edit_trim_in?: number
  edit_trim_out?: number
  edit_volume?: number
  text_layers?: TextLayerConfig[]
  voice_enabled?: boolean
  voice_language?: 'vi-VN' | 'ja-JP' | 'ko-KR' | 'en-US' | 'en-GB'
  voice_gender?: 'female' | 'male'
  voice_source?: 'manual' | 'subtitle' | 'translated_subtitle'
  voice_text?: string | null
  tts_engine?: 'edge' | 'piper' | 'xtts'
  voice_mix_mode?: 'replace_original' | 'keep_original_low'
  hook_apply_enabled?: boolean
  hook_overlay_enabled?: boolean

  // T1.4 — Audit 2026-06-08 closure (Batch A V8-B5 + UP26 + UP27 + v2).
  // Removed 19 dead fields from the wire surface (kept in the BE
  // RenderRequest model for Sacred Contract #2 replay safety, but
  // dropped from RenderRequestPublic + this interface because the
  // render pipeline never reads them). Phase-G zombies, UP26 Pro
  // Timeline Steering, asset_music_profile, energy_style /
  // output_language / narration_style. See backend/app/models/
  // render_public.py:FE_FACING_FIELDS comment block for the full
  // rationale and per-field evidence anchors.
  // `target_duration` is intentionally KEPT — it is targeted for LLM
  // prompt wiring by T2.4 (Sprint 2).
  target_platform?: 'tiktok' | 'youtube_shorts' | 'instagram_reels'
  ai_target_market?: string
  multi_variant?: boolean
  cta_enabled?: boolean
  cta_type?: 'auto' | 'comment' | 'part_2' | 'follow'

  // LLM segment selection — canonical names
  llm_enabled?: boolean | null
  llm_model?: string | null
  llm_language?: string | null
  llm_min_quality?: number | null
  llm_mode?: string | null
  ai_provider?: string | null

  // Strategic-1 + Strategic-1c — Audit 2026-06-08 closure. UP26 Pro
  // Timeline Steering — fully wired in Strategic-1c:
  //   clip_lock / clip_exclude — TimeRange arrays, wired through
  //     the LLM prompt (Strategic-1) and BE local filter
  //     (Strategic-1b).
  //   structure_bias — 'hook' | 'balanced' | 'story' — re-weights
  //     the ranking formula in pipeline_ranking.
  //   subtitle_emphasis — 'subtle' | 'balanced' | 'aggressive' —
  //     subtitle font-size multiplier applied at ASS generation.
  clip_lock?: TimeRange[] | null
  clip_exclude?: TimeRange[] | null
  structure_bias?: 'hook' | 'balanced' | 'story' | null
  subtitle_emphasis?: 'subtle' | 'balanced' | 'aggressive' | null

  // Creator Asset Intelligence (UP27) — surviving wired fields
  asset_logo_path?: string | null
  asset_intro_path?: string | null
  asset_outro_path?: string | null

  // Vision v2 — surviving wired fields
  target_duration?: number
  output_count?: number
  video_type?: string
  hook_strength?: string
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
  | 'partial'
  | 'failed'
  | 'interrupted'
  | 'cancelled'
  | 'cancelling'

export type JobErrorKind =
  | 'DOWNLOAD_FAILED'
  | 'WHISPER_FAILED'
  | 'SOURCE_NOT_FOUND'
  | 'FFMPEG_FAILED'
  | 'QA_FAILED'
  | 'VOICE_FAILED'
  | 'CANCELLED'
  | 'RENDER_FAILED'

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
  /** Populated by backend only when status === 'failed'. Additive — safe to add. */
  error_kind?: JobErrorKind | null
}

// ── JobPart (from GET /api/jobs/{job_id}/parts) ───────────────────────────────

export type JobPartStatus =
  | 'queued'
  | 'waiting'
  | 'cutting'
  | 'transcribing'
  | 'rendering'
  | 'done'
  | 'failed'
  | 'skipped'

export interface JobPart {
  part_no: number
  status: JobPartStatus
  progress_percent: number
  output_file: string
  updated_at: string
  hook_score: number
  viral_score: number
  motion_score: number
  duration: number
  message?: string
  // AI-selected clip metadata
  clip_name?: string
  ai_title?: string
  ai_reason?: string
  source?: string
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

// ── AI Output Ranking (from result_json.output_ranking[]) ────────────────────

export interface PartRankComponents {
  segment_viral_score: number
  hook_score: number
  retention_score: number
  speech_density_score: number
  market_score: number
  duration_fit_score: number
  continuity_score: number
  content_type_hint?: string
}

export interface PartRankResult {
  part_no: number
  output_rank: number           // 1 = best
  output_rank_score: number     // 0-100 composite engagement score
  is_best_clip: boolean
  is_best_output: boolean
  ranking_reason: string
  ranking_components: PartRankComponents
  dominant_signal?: string
  suppressed_signals?: string[]
  confidence_tier?: 'strong' | 'worth_testing' | 'experimental'
  score_margin?: number
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
  /** Job-level progress (0-100). Added 2026-06-15 (T2 visibility). */
  progress_percent: number
  /** Latest stage message (e.g. "Whisper transcribing… 120s elapsed"). */
  message: string
}

export interface JobsHistoryResponse {
  items: HistoryItem[]
  limit: number
  offset: number
  has_more: boolean
}

// ── Analytics Dashboard (Phase G) ────────────────────────────────────────────

export interface AnalyticsOverview {
  jobs: { completed: number; failed: number; running: number; total: number }
  feedback: { liked: number; disliked: number; total: number; like_rate: number }
  scores: { avg_viral: number; avg_hook: number; avg_retention: number; avg_rank_score: number; total_clips: number }
  editorial_overrides: Record<string, number>
}

export interface ScoreTrendPoint {
  date: string
  avg_viral: number
  avg_hook: number
  avg_retention: number
  avg_rank_score: number
  count: number
}

export interface FeedbackByHookPoint {
  hook_type: string
  likes: number
  dislikes: number
  total: number
  like_rate: number
}

export interface JobTrendPoint {
  date: string
  completed: number
  failed: number
  total: number
}

// ── Multi-Output Compare & Export (Phase F) ──────────────────────────────────

export interface OutputItem {
  part_no: number
  part_name: string
  status: string
  output_rank: number
  output_rank_score: number
  is_best_output: boolean
  viral_score: number
  hook_score: number
  retention_score: number
  start_sec: number
  end_sec: number
  duration: number
  output_file: string
  file_exists: boolean
  file_size_bytes: number
}

export interface OutputsResponse {
  job_id: string
  total_parts: number
  completed_parts: number
  outputs: OutputItem[]
}

// ── Render Presets (Phase E) ──────────────────────────────────────────────────

export interface RenderPresetParams {
  output_count?: number
  target_platform?: 'tiktok' | 'youtube_shorts' | 'instagram_reels'
  target_duration?: number
  video_type?: 'auto' | 'viral' | 'storytelling' | 'educational' | 'emotional' | 'high_retention'
  hook_strength?: 'aggressive' | 'balanced' | 'soft'
  add_subtitle?: boolean
  subtitle_style?: string
  llm_enabled?: boolean
  ai_provider?: 'gemini' | 'openai' | 'claude'
  ai_clip_min_duration_sec?: number
  ai_clip_max_duration_sec?: number
}

export interface RenderPreset {
  preset_id: string
  name: string
  description: string
  channel_code: string
  platform: string
  params: RenderPresetParams
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface PresetsResponse {
  presets: RenderPreset[]
}

// ── Disk Usage & Cleanup (Phase L) ───────────────────────────────────────────

export interface StorageStatusBucket {
  bytes: number
  files: number
  jobs: number
}

export interface StorageSummary {
  total_bytes: number
  total_files: number
  orphaned_db_refs: number
  by_status: Record<string, StorageStatusBucket>
}

export interface OutputDeleteResponse {
  job_id: string
  deleted_files: number
  freed_bytes: number
  missing_files: number
}

export interface StorageCleanupResponse {
  jobs_cleaned: number
  files_deleted: number
  freed_bytes: number
}

// ── Batch Render (Phase K) ────────────────────────────────────────────────────

export interface BatchRenderJobResult {
  asset_id: string
  job_id: string
  status: 'queued' | 'skipped'
  error?: string
}

export interface BatchRenderResponse {
  total: number
  queued: number
  skipped: number
  jobs: BatchRenderJobResult[]
}

// ── Per-Channel Creator Context (Phase I) ────────────────────────────────────

export interface CreatorContextPayload {
  creator_id: string
  channel_name: string
  brand_voice: string
  target_audience: string
  content_pillars: string[]
  market: string
  language: string
  notes: string
}

export interface CreatorContextEnvelope {
  is_configured: boolean
  creator_context: CreatorContextPayload
}

// ── Queue status ──────────────────────────────────────────────────────────────

export interface QueueStatus {
  max_concurrent: number
  active: number
  pending: number
  available_slots: number
}
