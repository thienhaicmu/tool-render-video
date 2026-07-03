/**
 * Content Studio API — POST /api/content/plan (plan-only, for the Review step).
 * The render itself goes through the shared render API (submitRender) with
 * render_format="content" + content_plan_override.
 */
import { apiFetch } from './client'

export interface ContentScene {
  index: number
  scene_title?: string
  role?: string
  narration: string
  emotion?: string
  reading_speed?: number
  pause_before?: number
  pause_after?: number
  emphasis?: string[]
  est_duration_sec?: number
  subtitle_style?: string
  visual_hint?: string
  visual_prompt?: string
  negative_prompt?: string
  asset_suggestion?: string
  // CS-E per-scene Asset Manager
  visual_source?: '' | 'color' | 'image' | 'video'
  visual_path?: string
  ken_burns?: boolean
  camera_hint?: string
  transition_hint?: string
  animation_hint?: string
}

export interface ContentPlan {
  schema_version?: number
  topic?: string
  tone?: string
  audience?: string
  language?: string
  video_style?: string
  total_target_sec?: number
  subtitle_style?: string
  bgm_mood?: string
  scenes: ContentScene[]
}

export interface ContentPlanRequest {
  script: string
  target_duration?: number
  voice_language?: string
  tone?: string
  ai_provider?: string | null
  llm_model?: string | null
}

/** Generate a ContentPlan from a script WITHOUT rendering (Review step). */
export async function generateContentPlan(req: ContentPlanRequest): Promise<{ plan: ContentPlan }> {
  return apiFetch<{ plan: ContentPlan }>('/api/content/plan', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export interface NarrationPreviewRequest {
  text: string
  voice_language?: string
  voice_gender?: 'female' | 'male'
  tts_engine?: string
  reading_speed?: number
}

export interface NarrationPreviewResult {
  token: string
  url: string
  duration_sec: number
}

/** Synthesize ONE scene's narration to previewable audio (Review Preview/Regenerate). */
export async function previewNarration(req: NarrationPreviewRequest): Promise<NarrationPreviewResult> {
  return apiFetch<NarrationPreviewResult>('/api/content/narration/preview', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ── CU-1: draft/project persistence ─────────────────────────────────────────

export interface ContentProjectPayload {
  title?: string
  script?: string
  plan?: ContentPlan | null
  config?: Record<string, unknown> | null
  status?: 'draft' | 'rendered'
  last_job_id?: string
}

export interface ContentProjectSummary {
  id: string
  title: string
  topic: string
  scenes: number
  status: string
  updated_at: string
}

export interface ContentProjectFull {
  id: string
  title: string
  script: string
  plan: ContentPlan | null
  config: Record<string, unknown> | null
  status: string
  last_job_id: string
  updated_at: string
}

export async function createProject(body: ContentProjectPayload): Promise<{ id: string }> {
  return apiFetch<{ id: string }>('/api/content/projects', { method: 'POST', body: JSON.stringify(body) })
}

export async function saveProject(id: string, body: ContentProjectPayload): Promise<{ id: string; ok: boolean }> {
  return apiFetch(`/api/content/projects/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) })
}

export async function getProject(id: string): Promise<ContentProjectFull> {
  return apiFetch<ContentProjectFull>(`/api/content/projects/${encodeURIComponent(id)}`)
}

export async function listProjects(): Promise<{ projects: ContentProjectSummary[] }> {
  return apiFetch<{ projects: ContentProjectSummary[] }>('/api/content/projects')
}

export async function deleteProject(id: string): Promise<void> {
  return apiFetch(`/api/content/projects/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// ── CU-14: publish intelligence ─────────────────────────────────────────────

export interface PublishMeta {
  title: string
  description: string
  tags: string[]
  thumbnail_scene_index: number
}

export async function publishMeta(req: {
  topic?: string; tone?: string; audience?: string
  voice_language?: string; narration_sample?: string
}): Promise<{ meta: PublishMeta }> {
  return apiFetch<{ meta: PublishMeta }>('/api/content/publish-meta', {
    method: 'POST', body: JSON.stringify(req),
  })
}
