/**
 * Story Studio API — /api/story/* (Story-to-Video).
 *
 * The render itself goes through the shared render API (submitRender) with
 * render_format="story" + story_plan_override (the approved storyboard). These
 * endpoints cover the pre-render review flow: analyze → storyboard → reference
 * sheet → narration preview. Types mirror the backend StoryPlan (asdict).
 */
import { apiFetch } from './client'

// ── Domain types (mirror backend app/domain/story_plan.py) ──────────────────

export interface StoryCharacter {
  id: string
  name: string
  description: string
  age?: string
  gender?: string
  voice_engine?: string
  voice_id?: string
  reference_image_path?: string
}

export interface StoryEnvironment {
  id: string
  name: string
  description: string
  reference_image_path?: string
}

export interface StoryBible {
  setting: string
  hook: string
  cta: string
  characters: StoryCharacter[]
  environments: StoryEnvironment[]
}

export interface Shot {
  index: number
  sid?: string
  shot_type: string
  narration: string
  speaker?: string
  emotion?: string
  reading_speed?: number
  pause_before?: number
  pause_after?: number
  est_duration_sec?: number
  camera?: string
  composition?: string
  lighting?: string
  characters?: string[]
  environment_ref?: string
  asset_type?: string
  quality_tier?: string
  visual_prompt?: string
  negative_prompt?: string
  visual_source?: string
  visual_path?: string
  transition_out?: string
  subtitle_style?: string
}

export interface StoryScene {
  index: number
  scene_title?: string
  role?: string
  setting_ref?: string
  emotion?: string
  characters?: string[]
  transition_out?: string
  shots: Shot[]
}

export interface StoryPlan {
  schema_version?: number
  series_id?: string
  chapter_no?: number
  language?: string
  art_style?: string
  aspect_ratio?: string
  reading_pace?: string
  topic?: string
  tone?: string
  story_bible: StoryBible
  scenes: StoryScene[]
}

// ── Request/response shapes ──────────────────────────────────────────────────

export interface AnalyzeRequest {
  chapter_text: string
  language?: string
  tone?: string
  series_id?: string
  chapter_no?: number
  ai_provider?: string
  llm_model?: string
}

export interface AnalyzeResponse {
  bible: StoryBible
  meta: Record<string, string>
}

export interface PlanRequest {
  chapter_text: string
  language?: string
  tone?: string
  art_style?: string
  series_id?: string
  chapter_no?: number
  aspect_ratio?: string
  reading_pace?: string
  bible?: StoryBible | null
  ai_provider?: string
  llm_model?: string
}

export interface NarrationAudit {
  weak: boolean
  rated: number
  overloaded: number
  sparse: number
  shots: Array<{ n: number; chars: number; load: number | null; flag: string }>
}

export interface PlanResponse {
  plan: StoryPlan
  scene_count: number
  shot_count: number
  estimated_total_sec: number
  narration_audit: NarrationAudit
}

export interface ReferenceSheetRequest {
  series_id?: string
  character_id?: string
  name?: string
  description?: string
  art_style?: string
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

// ── Calls ─────────────────────────────────────────────────────────────────────

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export const analyzeChapter = (req: AnalyzeRequest) =>
  post<AnalyzeResponse>('/api/story/analyze', req)

export const planStoryboard = (req: PlanRequest) =>
  post<PlanResponse>('/api/story/plan', req)

export const generateReferenceSheet = (req: ReferenceSheetRequest) =>
  post<{ path: string }>('/api/story/character/reference-sheet', req)

export const previewNarration = (req: NarrationPreviewRequest) =>
  post<NarrationPreviewResponse>('/api/story/narration/preview', req)
