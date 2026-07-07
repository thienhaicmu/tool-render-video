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
  story_bible?: {
    setting?: string
    hook?: string
    cta?: string
    characters?: { id?: string; name?: string; description?: string }[]
  }
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

/** AI's deterministic duration-fit result (reading-speed scaling to hit target). */
export interface DurationFit {
  changed: boolean
  before_sec: number
  after_sec: number
  target_sec: number
  applied_scale?: number | null
  in_tolerance?: boolean | null
  scaled_scenes?: number
}

/** AI's per-scene narration/timing audit (overloaded/sparse flags). */
export interface NarrationAuditScene {
  n: number
  chars: number
  capacity_chars?: number
  load?: number | null
  flag: 'overloaded' | 'sparse' | 'ok' | 'no_estimate'
}
export interface NarrationAudit {
  weak: boolean
  rated: number
  overloaded: number
  sparse: number
  scenes: NarrationAuditScene[]
}

export interface ContentPlanResponse {
  plan: ContentPlan
  duration_fit?: DurationFit | null
  narration_audit?: NarrationAudit | null
}

/** Generate a ContentPlan from a script WITHOUT rendering (Review step). The
 *  response also carries the AI's deterministic duration-fit + narration audit
 *  so the Review screen can show what the AI did. */
export async function generateContentPlan(req: ContentPlanRequest): Promise<ContentPlanResponse> {
  return apiFetch<ContentPlanResponse>('/api/content/plan', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ── Cost preflight (POST /api/content/estimate) ──────────────────────────────

export interface ContentEstimate {
  estimated_cost: number
  budget_cap: number
  scenes: number
  by_provider: Record<string, number>
  per_scene: { scene: number; provider: string; cost: number }[]
  estimated_duration_sec: number
}

export interface ContentEstimateRequest {
  plan?: ContentPlan
  script?: string
  target_duration?: number
  voice_language?: string
  visual_provider?: string
  budget_cap?: number
}

/** Preflight the AI cost + per-scene visual provider BEFORE rendering. Runs the
 *  same deterministic decision tree + budget guard the render uses (read-only —
 *  no render, no paid API call). */
export async function estimateContentCost(req: ContentEstimateRequest): Promise<ContentEstimate> {
  return apiFetch<ContentEstimate>('/api/content/estimate', {
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

// ── C1: per-scene visual preview ─────────────────────────────────────────────

export interface VisualPreviewRequest {
  prompt: string
  provider?: string
  aspect_ratio?: string
  seed?: number
  style?: string
  negative_prompt?: string
  imagen_tier?: string
}

export interface VisualPreviewResult {
  kind: 'image' | 'color' | 'video'
  provider: string
  token?: string
  url?: string   // present when kind === 'image'
  value?: string // background spec when it fell back (kind color/video)
}

/** Resolve ONE scene's visual via the render seam and return a previewable image
 *  (Review "Xem ảnh" / "Tạo lại"). Free for stock/Pollinations; a paid provider
 *  (Imagen) costs one image per call. */
export async function previewVisual(req: VisualPreviewRequest): Promise<VisualPreviewResult> {
  return apiFetch<VisualPreviewResult>('/api/content/visual/preview', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// CM-12: pin a previewed image (by token) as a durable per-scene asset. Returns
// the local file path to store in scene.visual_path (visual_source='image').
export async function pinVisual(token: string): Promise<{ path: string }> {
  return apiFetch<{ path: string }>('/api/content/visual/pin', {
    method: 'POST',
    body: JSON.stringify({ token }),
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

// ── P3.1: visual-provider availability (which sources are usable right now) ──

export interface VisualProviderInfo {
  available: boolean
  free: boolean
}
export interface VisualProvidersResult {
  providers: Record<string, VisualProviderInfo>
}

/** Which Content visual sources are usable right now (from the API keys in the
 *  server env). Read-only. The UI labels each "free / ready / needs key" and
 *  auto-selects the free stock provider when a key is configured. */
export async function getVisualProviders(): Promise<VisualProvidersResult> {
  return apiFetch<VisualProvidersResult>('/api/content/visual-providers')
}

// ── Item 7: content-plan polling / reattach fallback ────────────────────────
// GET /api/jobs/{jobId}/content-plan — the persisted ContentPlan, so the live
// monitor keeps its rich Director header + scene rows when the `plan` prop is
// null (job reattached from the topbar badge/dock) or the content.plan.ready WS
// event never arrives (WS→HTTP-polling downgrade). Mirrors getRecapPlan.
export interface ContentPlanFetchResult {
  job_id: string
  available: boolean
  plan?: ContentPlan | null
}
export async function getContentPlan(jobId: string): Promise<ContentPlanFetchResult> {
  return apiFetch<ContentPlanFetchResult>(`/api/jobs/${encodeURIComponent(jobId)}/content-plan`)
}
