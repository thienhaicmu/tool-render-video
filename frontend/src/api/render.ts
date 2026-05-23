/**
 * Render API — POST /api/render/process, cancel, status
 */
import { apiFetch } from './client'
import type { RenderRequest, RenderResponse, JobStatus } from '../types/api'

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
 * Get render job status via the render router.
 * GET /api/render/jobs/{jobId}
 */
export async function getRenderStatus(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/api/render/jobs/${encodeURIComponent(jobId)}`)
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
