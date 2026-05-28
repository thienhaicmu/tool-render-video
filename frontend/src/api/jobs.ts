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
  PartRankResult,
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
  const result = await apiFetch<{ items: JobPart[] }>(`/api/jobs/${encodeURIComponent(jobId)}/parts`)
  return result.items ?? []
}

/**
 * Parse result_json.output_ranking into a part_no-keyed map.
 * Returns empty map if result_json is absent, malformed, or ranking is unavailable.
 * GET /api/jobs/{jobId}
 */
export async function getJobRanking(jobId: string): Promise<Record<number, PartRankResult>> {
  const job = await getJob(jobId)
  try {
    const result = JSON.parse(job.result_json || '{}')
    const ranking: PartRankResult[] = result.output_ranking ?? []
    const map: Record<number, PartRankResult> = {}
    for (const entry of ranking) {
      if (entry.part_no != null) map[entry.part_no] = entry
    }
    return map
  } catch {
    return {}
  }
}

/**
 * AI decision summary for a completed job.
 * GET /api/jobs/{jobId}/ai-summary
 */
export interface AiRankEntry {
  part_no: number
  rank: number
  score: number
  reason: string
  dominant_signal: string
  confidence_tier: string
  is_best_clip: boolean
}

export interface RejectedSegment {
  part_no: number
  viral_score: number
  hook_score: number
  motion_score: number
  duration: number
  reject_reason: string
}

export interface HybridAnalysis {
  source: 'local' | 'cloud' | 'hybrid'
  confidence: number
  clips_analyzed: number
  warnings: string[]
}

export interface JobAiSummary {
  job_id: string
  available: boolean
  director_enabled: boolean
  story: Record<string, unknown>
  ai_ux: Record<string, unknown>
  output_count: number
  best_part_no: number | null
  best_score: number | null
  best_reason: string
  confidence_tier: string
  score_margin: number | null
  ranking_summary: AiRankEntry[]
  rejected_count: number
  rejected_segments: RejectedSegment[]
  output_ranking_warning: string
  hybrid_analysis?: HybridAnalysis
}

export async function getJobAiSummary(jobId: string): Promise<JobAiSummary> {
  return apiFetch<JobAiSummary>(`/api/jobs/${encodeURIComponent(jobId)}/ai-summary`)
}

/**
 * Delete the output file of a single rendered part.
 * DELETE /api/jobs/{jobId}/parts/{partNo}/output
 */
export async function deletePartOutput(
  jobId: string,
  partNo: number,
): Promise<{ job_id: string; part_no: number; deleted: boolean }> {
  return apiFetch(
    `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/output`,
    { method: 'DELETE' },
  )
}

// ── NOTE: Do NOT use GET /api/jobs (unbounded). Use getJobHistory() instead. ──
// ── NOTE: Do NOT use /api/jobs/{id}/parts/{no}/stream. Use /media endpoint.  ──
