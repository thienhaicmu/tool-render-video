/**
 * Maintenance / reset endpoints.
 *
 * clearHistory → POST /api/settings/clear-history. Deletes job + download +
 * asset history (and optionally the render cache) while preserving settings,
 * presets, and in-flight jobs. Added 2026-06-18 alongside the backend
 * db/history_repo.clear_history helper.
 */
import { apiFetch } from './client'

export interface ClearHistoryResult {
  ok: boolean
  deleted: Record<string, number>
  total_deleted: number
  preserve_active: boolean
  cache?: { removed: number; freed_bytes: number }
}

export async function clearHistory(opts?: {
  clearCache?: boolean
  preserveActive?: boolean
}): Promise<ClearHistoryResult> {
  return apiFetch<ClearHistoryResult>('/api/settings/clear-history', {
    method: 'POST',
    body: JSON.stringify({
      clear_cache: opts?.clearCache ?? false,
      preserve_active: opts?.preserveActive ?? true,
    }),
  })
}
