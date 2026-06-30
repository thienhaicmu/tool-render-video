/**
 * Performance API — read & persist the render speed-up toggles.
 *
 * Backend contract: backend/app/routes/settings.py
 *   GET /api/settings/performance → PerformanceEnvelope
 *   PUT /api/settings/performance (body=PerformancePayload) → PerformanceEnvelope
 *
 *   - hwdecode: P3 — decode the source on the iGPU (quality-neutral; the encoder
 *     side is untouched). Falls back to software decode automatically on failure.
 *   - qsv:      P0 — encode on the Intel iGPU (QSV). Much faster, but a hardware
 *     encoder is slightly less efficient than x264 at the same size, so it can
 *     look marginally softer. Opt-in.
 *
 * Saving applies the toggles to the live backend immediately (no restart).
 */
import { apiFetch } from './client'


/** Matches backend PerformancePayload (routes/settings.py). */
export interface PerformancePayload {
  hwdecode: boolean
  qsv: boolean
}


/** Matches backend PerformanceEnvelope (routes/settings.py). */
export interface PerformanceEnvelope {
  is_configured: boolean
  performance: PerformancePayload
}


export const BLANK_PERFORMANCE: PerformancePayload = {
  hwdecode: false,
  qsv: false,
}


export async function getPerformance(): Promise<PerformanceEnvelope> {
  return apiFetch<PerformanceEnvelope>('/api/settings/performance')
}


export async function putPerformance(
  body: PerformancePayload,
): Promise<PerformanceEnvelope> {
  return apiFetch<PerformanceEnvelope>('/api/settings/performance', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
