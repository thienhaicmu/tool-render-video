/**
 * Render API — POST /api/render/process, cancel, status
 */
import { apiFetch, BASE_URL } from './client'
import type { RenderRequest, RenderResponse } from '../types/api'

/**
 * Submit a new render job.
 * POST /api/render/process
 */
export async function submitRender(payload: RenderRequest): Promise<RenderResponse> {
  return apiFetch<RenderResponse>('/api/render/process', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * Cancel a running render job.
 * POST /api/render/{jobId}/cancel
 */
export async function cancelRender(jobId: string): Promise<void> {
  return apiFetch<void>(`/api/render/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

/**
 * Resume a previously interrupted job.
 * POST /api/render/resume/{jobId}
 */
export async function resumeRender(jobId: string): Promise<RenderResponse> {
  return apiFetch<RenderResponse>(`/api/render/resume/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  })
}

/**
 * Retry only failed parts of a job.
 * POST /api/render/retry/{jobId}
 */
export async function retryRender(jobId: string): Promise<RenderResponse> {
  return apiFetch<RenderResponse>(`/api/render/retry/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  })
}

export interface PrepareSourceResponse {
  session_id: string
  duration: number
  title: string
  export_dir: string
}

export async function prepareSource(
  body: {
    source_mode: 'youtube' | 'local'
    youtube_url?: string
    source_video_path?: string
  },
  signal?: AbortSignal,
): Promise<PrepareSourceResponse> {
  return apiFetch<PrepareSourceResponse>('/api/render/prepare-source', {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export async function cancelPrepareSource(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/render/prepare-source/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

export function getPreviewVideoUrl(sessionId: string): string {
  return `${BASE_URL}/api/render/preview-video/${encodeURIComponent(sessionId)}`
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
}

export async function getPreviewTranscript(
  sessionId: string,
): Promise<{ segments: TranscriptSegment[]; status?: string }> {
  return apiFetch<{ segments: TranscriptSegment[]; status?: string }>(
    `/api/render/preview-transcript/${encodeURIComponent(sessionId)}`,
  )
}

export interface CloudAiTestResult {
  ok: boolean
  provider: string
  model?: string
  latency_ms: number
  error?: string
}

export async function testCloudAi(
  provider: 'groq' | 'gemini' | 'openai',
  api_key: string,
  model?: string,
): Promise<CloudAiTestResult> {
  return apiFetch<CloudAiTestResult>('/api/render/test-cloud-ai', {
    method: 'POST',
    body: JSON.stringify({ provider, api_key, model: model || null }),
  })
}
