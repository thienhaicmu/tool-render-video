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
}

export interface SettingDef {
  id: string
  name: string
  canonical_desc: string
  scene_kind?: string  // library scene token (procedural/fuzzy match)
  asset?: string       // library-pick: AI-chosen library background slug ('' = none)
}

export interface Visual {
  id: string
  setting_id: string
  prompt: string
  negative_prompt: string
  character_ids: string[]
  tier: string
}

export interface Beat {
  id: string
  narration: string
  speaker_id: string
  visual_id: string
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
  cues: Cue[]
  total_sec: number
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
}

export interface VisualPreviewRequest {
  prompt: string
  negative_prompt?: string
  art_style?: string
  aspect_ratio?: string
  tier?: string
  // Phase 2 — draft/final split. Omit → backend defaults to the FREE provider
  // (Pollinations) so storyboard previews/regenerates cost $0.
  provider?: 'pollinations' | 'gpt_image'
}

export interface VisualPreviewResponse {
  token: string
  url: string
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

export interface ReferenceSheetRequest {
  series_id?: string
  character_id?: string
  name?: string
  description?: string
  art_style?: string
  // true → cutout-ready CHARACTER MASTER (transparent PNG) for overlay/preview.
  transparent?: boolean
  // A5 — 0 = canonical master; >0 regenerates a different look to pick from.
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

/** Generate ONE key-visual image from a prompt (storyboard preview / regenerate). */
export const previewVisual = (req: VisualPreviewRequest) =>
  post<VisualPreviewResponse>('/api/story/visual/preview', req)

/** Synthesize ONE beat's narration to previewable audio. */
export const previewNarration = (req: NarrationPreviewRequest) =>
  post<NarrationPreviewResponse>('/api/story/narration/preview', req)

/** Generate a Character Reference Sheet, or (transparent=true) a cutout-ready
 * character master. Returns the durable path and, for a master, a viewable url. */
export const generateReferenceSheet = (req: ReferenceSheetRequest) =>
  post<{ path: string; url?: string }>('/api/story/character/reference-sheet', req)

/** Reattach: fetch a job's persisted StoryPlan v2 (polling fallback). */
export const fetchJobStoryPlan = (jobId: string) =>
  apiFetch<JobStoryPlanResponse>(`/api/jobs/${encodeURIComponent(jobId)}/story-plan`)

/** Available voices for the language's TTS engine (per-character voice override). */
export const getStoryVoices = (language: string) =>
  apiFetch<StoryVoicesResponse>(`/api/story/voices?language=${encodeURIComponent(language)}`)
