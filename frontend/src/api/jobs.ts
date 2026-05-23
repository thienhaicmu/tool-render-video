/**
 * Jobs API — list, get, quality, delete
 */
import { apiFetch } from './client'
import type {
  JobStatus,
  JobPart,
  JobsHistoryResponse,
  QualityReport,
  QualitySummary,
  QueueStatus,
} from '../types/api'

/**
 * Get a single job by ID.
 * GET /api/jobs/{jobId}
 */
export async function getJob(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`)
}

/**
 * Paginated job history. ALWAYS use this instead of listJobs() for history UI.
 * GET /api/jobs/history?limit=20&offset=0
 */
export async function getJobHistory(
  limit = 20,
  offset = 0,
): Promise<JobsHistoryResponse> {
  const params = new URLSearchParams({
    limit: String(Math.max(1, Math.min(100, limit))),
    offset: String(Math.max(0, offset)),
  })
  return apiFetch<JobsHistoryResponse>(`/api/jobs/history?${params}`)
}

/**
 * Get queue depth.
 * GET /api/jobs/queue/status
 */
export async function getQueueStatus(): Promise<QueueStatus> {
  return apiFetch<QueueStatus>('/api/jobs/queue/status')
}

/**
 * Single-part quality report. Call on-demand only — do NOT poll this endpoint.
 * GET /api/jobs/{jobId}/parts/{partNo}/quality
 */
export async function getJobPartQuality(
  jobId: string,
  partNo: number,
): Promise<QualityReport> {
  return apiFetch<QualityReport>(
    `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/quality`,
  )
}

/**
 * Aggregated quality summary for a job.
 * GET /api/jobs/{jobId}/quality?include_reports=false
 * Call on-demand only — do NOT poll this endpoint.
 */
export async function getJobQualitySummary(
  jobId: string,
  includeReports = false,
): Promise<QualitySummary> {
  const params = new URLSearchParams({ include_reports: String(includeReports) })
  return apiFetch<QualitySummary>(
    `/api/jobs/${encodeURIComponent(jobId)}/quality?${params}`,
  )
}

/**
 * Delete a completed/failed/cancelled job and optionally its output files.
 * DELETE /api/jobs/{jobId}
 */
export async function deleteJob(
  jobId: string,
  deleteFiles = true,
): Promise<{ job_id: string; deleted: boolean; deleted_files: number; skipped_files: number }> {
  const params = new URLSearchParams({ delete_files: String(deleteFiles) })
  return apiFetch(`/api/jobs/${encodeURIComponent(jobId)}?${params}`, {
    method: 'DELETE',
  })
}

/**
 * Get all parts for a job.
 * GET /api/jobs/{jobId}/parts
 */
export async function getJobParts(jobId: string): Promise<JobPart[]> {
  return apiFetch<JobPart[]>(`/api/jobs/${encodeURIComponent(jobId)}/parts`)
}

// ── NOTE: Do NOT use GET /api/jobs (unbounded). Use getJobHistory() instead. ──
// ── NOTE: Do NOT use /api/jobs/{id}/parts/{no}/stream. Use /media endpoint.  ──
