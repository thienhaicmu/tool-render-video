/**
 * Editor feature utility functions — all pure, no side effects.
 */

/** Build media URL for a job/part */
export function buildMediaUrl(jobId: string, partNo: number): string {
  return `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`
}

/** Build thumbnail URL */
export function buildThumbnailUrl(jobId: string, partNo: number): string {
  return `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/thumbnail`
}

/** Format time as mm:ss */
export function formatTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Clamp number to range */
export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val))
}

/** Validate trim range — returns null if valid, error message if invalid */
export function validateTrim(start: number, end: number, duration: number): string | null {
  if (start < 0) return 'Start time cannot be negative'
  if (duration > 0 && end > duration) return `End time cannot exceed ${formatTime(duration)}`
  if (start >= end) return 'Start must be before end'
  if (end - start < 1) return 'Trim must be at least 1 second'
  return null
}
