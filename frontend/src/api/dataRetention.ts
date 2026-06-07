/**
 * Data-retention API — read & persist the auto-prune setting for
 * completed jobs older than N days.
 *
 * Backend contract: backend/app/routes/settings.py (Batch 10R MT-7 UI)
 *   GET /api/settings/data-retention → DataRetentionEnvelope
 *   PUT /api/settings/data-retention (body=DataRetentionPayload)
 *                                    → DataRetentionEnvelope
 *
 * The wire shape mirrors creatorContext.ts so the Settings screen
 * sections look and behave the same. ``job_retention_days``:
 *   - 0      = retention disabled (default; the safe initial state).
 *   - 1-365  = the periodic cleanup loop prunes terminal-status jobs
 *              whose updated_at is older than N days.
 * Values outside the range are clamped server-side; the FE renders the
 * clamped value back.
 */
import { apiFetch } from './client'


/** Matches backend DataRetentionPayload (routes/settings.py). */
export interface DataRetentionPayload {
  job_retention_days: number
}


/** Matches backend DataRetentionEnvelope (routes/settings.py). */
export interface DataRetentionEnvelope {
  is_configured: boolean
  data_retention: DataRetentionPayload
}


/** Default-shaped payload — what the BE returns on a fresh DB. */
export const BLANK_DATA_RETENTION: DataRetentionPayload = {
  job_retention_days: 0,
}


export async function getDataRetention(): Promise<DataRetentionEnvelope> {
  return apiFetch<DataRetentionEnvelope>('/api/settings/data-retention')
}


export async function putDataRetention(
  body: DataRetentionPayload,
): Promise<DataRetentionEnvelope> {
  return apiFetch<DataRetentionEnvelope>('/api/settings/data-retention', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
