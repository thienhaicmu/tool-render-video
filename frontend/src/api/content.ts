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
