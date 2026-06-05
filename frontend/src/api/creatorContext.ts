/**
 * CreatorContext API — read & persist the channel persona settings
 * that the AI Director consumes before emitting a RenderPlan.
 *
 * Backend contract: backend/app/routes/settings.py (Sprint 3-FE)
 *   GET /api/settings/creator-context → CreatorContextEnvelope
 *   PUT /api/settings/creator-context (body=CreatorContextPayload)
 *                                     → CreatorContextEnvelope
 *
 * Field-for-field mirror of the Pydantic model — keep these in sync
 * when adding fields. The defaults below match the backend so a
 * "blank" form here PUTs the same shape the route's empty body would.
 */
import { apiFetch } from './client'

/** Matches backend CreatorContextPayload (routes/settings.py). */
export interface CreatorContextPayload {
  creator_id: string
  channel_name: string
  brand_voice: string
  target_audience: string
  content_pillars: string[]
  market: string
  language: string
  notes: string
}

/** Matches backend CreatorContextEnvelope (routes/settings.py). */
export interface CreatorContextEnvelope {
  is_configured: boolean
  creator_context: CreatorContextPayload
}

/** Default-shaped payload — exactly what the backend returns on a fresh DB. */
export const BLANK_CREATOR_CONTEXT: CreatorContextPayload = {
  creator_id: '',
  channel_name: '',
  brand_voice: '',
  target_audience: '',
  content_pillars: [],
  market: '',
  language: '',
  notes: '',
}

export async function getCreatorContext(): Promise<CreatorContextEnvelope> {
  return apiFetch<CreatorContextEnvelope>('/api/settings/creator-context')
}

export async function putCreatorContext(
  body: CreatorContextPayload,
): Promise<CreatorContextEnvelope> {
  return apiFetch<CreatorContextEnvelope>('/api/settings/creator-context', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
