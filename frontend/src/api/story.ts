/**
 * Story Studio API — /api/story/* (Story-to-Video v2, Super-Prompt + Cue Sheet).
 *
 * The render itself goes through the shared render API (submitRender) with
 * render_format="story" (+ optional story_plan_override = the approved v2 plan).
 * These endpoints cover the pre-render review flow: one super plan call
 * (source A=paste chapter / B=idea) → per-Visual preview → per-beat narration
 * preview. Types mirror the backend app/domain/story_plan_v2.py.
 */
import { apiFetch } from './client'

// ── Domain types (mirror backend app/domain/story_plan_v2.py) ────────────────

export interface CharacterDef {
  id: string
  name: string
  canonical_desc: string
  age?: string
  gender?: string
  voice_gender?: string
  voice_style?: string
  archetype?: string   // library role token (procedural/fuzzy match)
  asset?: string       // library-pick: AI-chosen library character slug ('' = none)
  visual_identity_id?: string // approved Visual Library V3 identity
}

export interface SettingDef {
  id: string
  name: string
  canonical_desc: string
  scene_kind?: string  // library scene token (procedural/fuzzy match)
  asset?: string       // library-pick: AI-chosen library background slug ('' = none)
  visual_scene_identity_id?: string // approved Visual Library V3 scene identity
}

export interface Visual {
  id: string
  setting_id: string
  prompt: string
  negative_prompt: string
  character_ids: string[]
  tier: string
}

export interface RelationshipDef {
  source_id: string
  target_id: string
  kind: string
  status: string
}

export interface SequenceDef {
  id: string
  role: string
  purpose: string
  scene_ids: string[]
}

export interface SceneDef {
  id: string
  sequence_id: string
  setting_id: string
  purpose: string
  participant_ids: string[]
  beat_ids: string[]
  shot_ids: string[]
  time_of_day: string
  entry_state: string
  exit_state: string
  continuity_key: string
}

export interface ShotDef {
  id: string
  scene_id: string
  beat_ids: string[]
  visual_id: string
  shot_size: string
  angle: string
  lens: string
  camera_position: string
  blocking: string
  eyeline: string
  axis: string
  composition: string
  motion_intent: string
}

export interface CharacterStateDef {
  character_id: string
  scene_id: string
  objective: string
  emotion: string
  position: string
  continuity_notes: string
}

/** P1 — one spoken line inside a Beat (a beat = one shot that may hold several
 * dialogue turns). speaker_id '' = narrator. */
export interface Line {
  speaker_id: string
  text: string
  emotion: string
  pose?: string
}

export interface Beat {
  id: string
  narration: string
  speaker_id: string
  visual_id: string
  shot_id?: string
  focus: string
  motion: string
  emotion: string
  pose?: string        // N4+ per-beat speaker gesture (overlay mode)
  reading_speed: number
  pause_after: number
  hold_sec: number
  transition_in: string
  hook: boolean
  hook_text: string
  lines?: Line[]        // P1 — multi-line dialogue; empty/absent → legacy single line
}

/** P1 — a beat's spoken lines, normalised. Mirrors the backend Beat.effective_lines():
 * uses `lines` when present (dropping blanks), else the legacy single narration line. */
export function beatLines(b: Beat): Line[] {
  if (b.lines && b.lines.length) return b.lines.filter((l) => (l.text || '').trim().length > 0)
  if ((b.narration || '').trim()) return [{ speaker_id: b.speaker_id, text: b.narration, emotion: b.emotion, pose: b.pose }]
  return []
}

export interface Cue {
  beat_id: string
  visual_id: string
  start_sec: number
  end_sec: number
  transition: string
  hook: boolean
  hook_text: string
}

export interface RenderState {
  visual_assets: Record<string, string>
  voices: Record<string, [string, string]>
  refs: Record<string, string>
  masters?: Record<string, string>   // A5 — char_id → locked transparent master path
  // GĐ3 — char_id → matched_exact | matched | needs_approval | missing
  asset_status?: Record<string, string>
  cues: Cue[]
  total_sec: number
}

/** GĐ3 — deterministic character→library-asset resolution report. */
export interface AssetResolution {
  statuses: Record<string, string>
  needs_approval: string[]
  missing: string[]
  characters: { id: string; name: string; asset: string; status: string }[]
  scenes?: { id: string; asset: string; status: string }[]
}

export interface StoryPlanV2 {
  schema_version: number
  seed: number
  series_id: string
  chapter_no: number
  language: string
  art_style: string
  aspect_ratio: string
  topic: string
  tone: string
  characters: CharacterDef[]
  settings: SettingDef[]
  visuals: Visual[]
  relationships?: RelationshipDef[]
  sequences?: SequenceDef[]
  scenes?: SceneDef[]
  shots?: ShotDef[]
  character_states?: CharacterStateDef[]
  timeline: Beat[]
  render: RenderState
}

// ── Request/response shapes ──────────────────────────────────────────────────

export interface StoryPlanRequest {
  source: 'paste' | 'idea'
  chapter_text?: string
  idea?: string
  duration_sec?: number
  genre?: string
  language?: string
  art_style?: string
  aspect_ratio?: string
  subtitle_mode?: string
  ceiling?: number | null
  series_id?: string
  chapter_no?: number
  ai_provider?: string
  llm_model?: string
  voice_mode?: 'narrator' | 'dialogue'   // P1 — narrator = one voice reads all; dialogue = per-character voices
}

export interface StoryPlanResponse {
  plan: StoryPlanV2
  image_count: number
  beat_count: number
  estimated_total_sec: number
  // Source-truncation transparency: true when the pasted chapter / idea exceeded
  // the super-prompt limit and its tail was cut (FE warns the user to split it).
  source_truncated?: boolean
  source_chars?: number
  source_char_limit?: number
  // P3 — soft semantic lint of the plan (non-blocking): orphan visuals,
  // generic-look speakers, looping narration. Shown as review hints.
  warnings?: string[]
  // GĐ3 — engine-resolved character assets + per-character state (null = resolver off)
  asset_resolution?: AssetResolution | null
  authoring_mode?: 'compiler' | 'single_pass' | 'compiler_fallback_single_pass' | string
  readiness?: { ready?: boolean; passes?: string[]; warns?: string[]; fails?: string[] } | null
  quality_signals?: {
    scene_shot?: {
      scenes?: number
      shots?: number
      beat_coverage?: number
      establishing_rate?: number
      unique_sizes?: number
      unique_angles?: number
      shot_score?: number
    }
  }
  planning_trace?: StoryPlanningTrace
  cost_preflight?: {
    estimated_llm_calls?: number
    actual_llm_calls?: number
    estimated_llm_input_tokens?: number
    estimated_llm_output_tokens?: number
    estimated_llm_cost_usd?: number
    estimated_cost_usd?: number
  }
}

export interface StoryPlanningEvent {
  event: string
  stage?: string
  status?: string
  call_no?: number
  latency_ms?: number
  provider?: string
  model?: string
  passed?: boolean
  reasons?: string[]
}

export interface StoryPlanningTrace {
  run_id: string
  status: string
  phase: string
  message: string
  actual_llm_calls: number
  authoring_mode?: string
  selected_provider?: string
  selected_model?: string
  role_routes?: Record<string, { provider?: string; model?: string }>
  compiler_fallback?: boolean
  artifacts_available?: boolean
  events: StoryPlanningEvent[]
}

// Paste-JSON feature: preflight a hand-pasted StoryPlan before render (no AI).
export interface StoryValidateResponse {
  ok: boolean
  errors: string[]
  warnings: string[]
  estimated_total_sec: number
  beat_count: number
  character_count: number
  image_count: number
  asset_resolution?: AssetResolution | null   // GĐ3
  plan_normalized: StoryPlanV2 | null   // scrubbed + reset — render THIS
}

// Story Mode is SVG-only: the Review composes procedural SVG key-visuals server-side
// (offline, $0, WYSIWYG) from the plan being edited.
export interface SvgPreviewRequest {
  plan: StoryPlanV2
  visual_ids?: string[]   // subset to compose ([]/omit = all)
}

export interface SvgPreviewItem {
  visual_id: string
  token: string
  url: string
}

export interface SvgPreviewResponse {
  items: SvgPreviewItem[]
}

export interface NarrationPreviewRequest {
  text: string
  language?: string
  gender?: string
  voice_id?: string
  reading_speed?: number
}

export interface NarrationPreviewResponse {
  token: string
  url: string
  engine: string
  duration_sec: number
}

// Cutout-ready transparent CHARACTER MASTER (procedural SVG chibi) — the same asset
// the render overlays. Derived from archetype/gender (+ region/genre palette).
export interface CharacterMasterRequest {
  character_id?: string
  name?: string
  description?: string   // kept for compatibility (unused by the SVG builder)
  archetype?: string
  gender?: string
  region?: string
  genre?: string
  art_style?: string
  // 0 = canonical stand pose; >0 rotates the pose so "regenerate" yields a new look.
  variant?: number
}

export interface JobStoryPlanResponse {
  job_id: string
  available: boolean
  plan: StoryPlanV2 | null
}

export interface StoryVoicesResponse {
  engine: string
  female: string[]
  male: string[]
}

// ── Calls ─────────────────────────────────────────────────────────────────────

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

/** One super plan call → StoryPlan v2 (source A=paste chapter / B=idea). */
export const planStory = (req: StoryPlanRequest) =>
  post<StoryPlanResponse>('/api/story/plan', req)

// ── GĐ1f: async plan — the compiler runs 3 sequential LLM calls (a long chapter
// can take minutes), so the FE starts a job and polls instead of holding one
// HTTP request open. Same request/response shapes as the sync endpoint.
export interface StoryPlanJobStart { plan_job_id: string; status: string }
export interface StoryPlanJobStatus {
  status: 'running' | 'done' | 'error'
  result?: StoryPlanResponse
  error?: string
  status_code?: number
  progress?: StoryPlanningTrace
}

export const planStoryStart = (req: StoryPlanRequest) =>
  post<StoryPlanJobStart>('/api/story/plan/async', req)

export const planStoryStatus = (jobId: string) =>
  apiFetch<StoryPlanJobStatus>(`/api/story/plan/async/${encodeURIComponent(jobId)}`)

/** Start an async plan job and poll it to completion (2s interval, 15 min cap).
 * Resolves with the same StoryPlanResponse as planStory; rejects on error. */
export async function planStoryAsync(
  req: StoryPlanRequest,
  onProgress?: (progress: StoryPlanningTrace) => void,
): Promise<StoryPlanResponse> {
  const { plan_job_id } = await planStoryStart(req)
  const deadline = Date.now() + 15 * 60_000
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000))
    const s = await planStoryStatus(plan_job_id)
    if (s.progress) onProgress?.(s.progress)
    if (s.status === 'done' && s.result) return s.result
    if (s.status === 'error') throw new Error(s.error || 'Story planning failed')
    if (Date.now() > deadline) throw new Error('Story planning timed out')
  }
}

/** Preflight a hand-pasted StoryPlan JSON (paste-JSON feature) before render — no AI. */
export const validateStoryPlan = (plan: string | StoryPlanV2, has_base_video = false) =>
  post<StoryValidateResponse>('/api/story/validate', { plan, has_base_video })

/** Compose the procedural SVG key-visual(s) for a plan (Review preview, offline $0). */
export const svgPreview = (req: SvgPreviewRequest) =>
  post<SvgPreviewResponse>('/api/story/visual/svg-preview', req)

/** Synthesize ONE beat's narration to previewable audio. */
export const previewNarration = (req: NarrationPreviewRequest) =>
  post<NarrationPreviewResponse>('/api/story/narration/preview', req)

/** Compose a cutout-ready transparent character master (procedural SVG chibi).
 * Returns the durable path + a viewable url. */
export const generateCharacterMaster = (req: CharacterMasterRequest) =>
  post<{ path: string; url?: string }>('/api/story/character/reference-sheet', req)

/** Reattach: fetch a job's persisted StoryPlan v2 (polling fallback). */
export const fetchJobStoryPlan = (jobId: string) =>
  apiFetch<JobStoryPlanResponse>(`/api/jobs/${encodeURIComponent(jobId)}/story-plan`)

/** Available voices for the language's TTS engine (per-character voice override). */
export const getStoryVoices = (language: string) =>
  apiFetch<StoryVoicesResponse>(`/api/story/voices?language=${encodeURIComponent(language)}`)
