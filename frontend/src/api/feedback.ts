/**
 * Clip feedback API — submit, fetch, delete user ratings on rendered clip parts.
 *
 * Backend contract: backend/app/routes/feedback.py
 *   POST   /api/feedback/jobs/{jobId}/parts/{partNo}  → FeedbackRecord
 *   GET    /api/feedback/jobs/{jobId}/parts/{partNo}  → FeedbackRecord | null
 *   DELETE /api/feedback/jobs/{jobId}/parts/{partNo}  → 204
 */
import { apiFetch } from './client'

/** Matches backend FeedbackSubmit (routes/feedback.py:33-41). */
export interface FeedbackSubmitBody {
  rating: 1 | -1
  hook_type?: string
  clip_type?: string
  channel_code?: string
  goal?: string
  start_sec?: number
  end_sec?: number
  duration_sec?: number
}

/** Matches backend FeedbackRecord (routes/feedback.py:44-55). */
export interface FeedbackRecord {
  job_id: string
  part_no: number
  channel_code: string
  goal: string
  rating: 1 | -1
  hook_type: string
  clip_type: string
  start_sec: number
  end_sec: number
  duration_sec: number
  rated_at: string
}

function feedbackPath(jobId: string, partNo: number): string {
  return `/api/feedback/jobs/${encodeURIComponent(jobId)}/parts/${partNo}`
}

export async function submitClipFeedback(
  jobId: string,
  partNo: number,
  body: FeedbackSubmitBody,
): Promise<FeedbackRecord> {
  return apiFetch<FeedbackRecord>(feedbackPath(jobId, partNo), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Returns null when the part has no rating yet (backend returns JSON null). */
export async function getClipFeedback(
  jobId: string,
  partNo: number,
): Promise<FeedbackRecord | null> {
  return apiFetch<FeedbackRecord | null>(feedbackPath(jobId, partNo))
}

export async function deleteClipFeedback(
  jobId: string,
  partNo: number,
): Promise<void> {
  await apiFetch<void>(feedbackPath(jobId, partNo), { method: 'DELETE' })
}
