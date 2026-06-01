/**
 * render-v2.ts — API client for v2 render pipeline.
 * Endpoints: /api/v2/render  (POST, GET, DELETE)
 *
 * Maps frontend ConfigState → v2 RenderRequest (simpler schema, local-file only).
 */
import { apiFetch } from './client'
import type { ConfigState, Source } from '../features/clip-studio/render/types'

// ── v2 types ──────────────────────────────────────────────────────────────────

export interface V2RenderRequest {
  source_path:       string
  output_dir:        string
  output_count?:     number
  min_part_sec?:     number
  max_part_sec?:     number
  groq_enabled?:     boolean
  groq_api_key?:     string
  groq_model?:       string
  groq_language?:    string
  groq_min_score?:   number
  ai_director_enabled?: boolean
  subtitle_enabled?: boolean
  voice_enabled?:    boolean
  platform?:         string
  video_codec?:      string
  aspect_ratio?:     string
}

export interface V2SubmitResponse {
  job_id: string
  status: string
}

export interface V2Output {
  path:               string
  output_rank_score:  number
  is_best_output:     boolean
  is_best_clip:       boolean
  qa_passed:          boolean
}

export interface V2RenderResult {
  job_id:             string
  status:             string
  total_parts:        number
  success_parts:      number
  failed_parts:       number
  best_output?:       string
  output_rank_score:  number
  is_best_output:     boolean
  is_best_clip:       boolean
  outputs:            V2Output[]
}

export interface V2JobResponse {
  job_id:     string
  status:     string
  created_at: number
  updated_at: number
  error?:     string
  result?:    V2RenderResult
  events:     Array<{ stage: string; ts: number; [k: string]: unknown }>
}

export interface V2JobListItem {
  job_id:     string
  status:     string
  created_at: number
  source:     string
}

// ── Ratio mapping ─────────────────────────────────────────────────────────────

const RATIO_API: Record<string, string> = {
  r916: '9:16',
  r34:  '3:4',
  r45:  '4:5',
  r11:  '1:1',
  r169: '16:9',
}

// ── Config → V2RenderRequest ──────────────────────────────────────────────────

export function buildV2Payload(cfg: ConfigState, source: Source): V2RenderRequest {
  return {
    source_path:      source.value,
    output_dir:       cfg.outputDir || 'output',
    output_count:     cfg.outputCount,
    min_part_sec:     cfg.minSec,
    max_part_sec:     cfg.maxSec,
    groq_enabled:     cfg.groqEnabled,
    groq_api_key:     cfg.aiCloudApiKey || undefined,
    groq_model:       cfg.groqModel || undefined,
    groq_language:    cfg.groqContentLanguage !== 'auto' ? cfg.groqContentLanguage : undefined,
    groq_min_score:   0.6,
    ai_director_enabled: cfg.aiEnabled,
    subtitle_enabled: cfg.subEnabled,
    voice_enabled:    cfg.narrEnabled,
    platform:         cfg.platform,
    video_codec:      'h264',
    aspect_ratio:     RATIO_API[cfg.ratio] ?? '9:16',
  }
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function submitRenderV2(payload: V2RenderRequest): Promise<string> {
  const res = await apiFetch<V2SubmitResponse>('/api/v2/render', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.job_id
}

export async function getJobV2(jobId: string): Promise<V2JobResponse> {
  return apiFetch<V2JobResponse>(`/api/v2/render/${encodeURIComponent(jobId)}`)
}

export async function cancelRenderV2(jobId: string): Promise<void> {
  await apiFetch<V2SubmitResponse>(`/api/v2/render/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
  })
}

export async function listJobsV2(limit = 20): Promise<V2JobListItem[]> {
  return apiFetch<V2JobListItem[]>(`/api/v2/render?limit=${limit}`)
}
