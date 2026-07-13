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
