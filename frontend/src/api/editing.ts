/**
 * Editing API — trim, re-render selection, export clip.
 *
 * POST /api/jobs/{jobId}/parts/{partNo}/trim
 * POST /api/jobs/{jobId}/parts/{partNo}/rerender
 * POST /api/jobs/{jobId}/parts/{partNo}/export
 */
import { apiFetch } from './client'

export interface TrimRequest {
  start_sec: number
  end_sec: number
  output_mode?: 'new_job' | 'replace'
}

export interface TrimResult {
  status: string
  job_id: string
  part_no: number
  output_file: string
  duration_sec: number
  trim_start_sec: number
  trim_end_sec: number
  output_mode: string
}

export interface RerenderRequest {
  start_sec: number
  end_sec: number
  effect_preset?: string
  subtitle_style?: string
}

export interface RerenderResult {
  status: string
  new_job_id: string
  parent_job_id: string
  parent_part_no: number
  trim_start_sec: number
  trim_end_sec: number
}

export interface ExportRequest {
  destination_dir: string
  /** Publish v1 — platform subfolder + filename tag (additive, optional). */
  platform_preset?: 'tiktok' | 'youtube_shorts' | 'instagram_reels'
  /** Publish v1 — write a .txt sidecar (AI title/reason + hashtags). */
  write_metadata?: boolean
}

export interface ExportResult {
  status: string
  job_id: string
  part_no: number
  source_file: string
  exported_to: string
  destination_dir: string
}

/**
 * Trim a rendered clip to [start_sec, end_sec].
 * output_mode defaults to 'new_job' (never overwrites original).
 */
export async function trimJobPart(
  jobId: string,
  partNo: number,
  req: TrimRequest,
): Promise<TrimResult> {
  return apiFetch<TrimResult>(
    `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/trim`,
    { method: 'POST', body: JSON.stringify({ output_mode: 'new_job', ...req }) },
  )
}

/**
 * Create a new render job for a selected segment of a completed part.
 * Returns immediately — poll /api/jobs/{new_job_id} for status.
 */
export async function rerenderSelection(
  jobId: string,
  partNo: number,
  req: RerenderRequest,
): Promise<RerenderResult> {
  return apiFetch<RerenderResult>(
    `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/rerender`,
    { method: 'POST', body: JSON.stringify(req) },
  )
}

/**
 * Export a rendered clip to a local directory.
 * destination_dir must be an absolute path within safe roots.
 */
export async function exportClip(
  jobId: string,
  partNo: number,
  req: ExportRequest,
): Promise<ExportResult> {
  return apiFetch<ExportResult>(
    `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/export`,
    { method: 'POST', body: JSON.stringify(req) },
  )
}
