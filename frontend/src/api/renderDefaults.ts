/**
 * Render defaults — persisted form pre-fill values for the Configure step
 * of the render workflow (S2.1).
 *
 * Endpoint surface: /api/settings/render-defaults (GET + PUT). Backend
 * stores in creator_prefs.prefs_json nested under "render_defaults"
 * (see db/creator_repo.py:upsert_render_defaults). All fields are
 * optional → null means "no preference, fall back to UI default". A PUT
 * with `{}` clears the saved defaults entirely.
 *
 * Sacred Contract #2 note: this payload is NEVER merged into
 * RenderRequest server-side — the FE applies it as form pre-fill only
 * and the actual render submit still validates against RenderRequestPublic.
 */
import { apiFetch } from './client'

export interface RenderDefaultsPayload {
  aspect_ratio: string | null
  preset: string | null
  voice_provider: string | null
  voice_id: string | null
  subtitle_style: string | null
  llm_provider: string | null
}

export interface RenderDefaultsEnvelope {
  is_configured: boolean
  render_defaults: RenderDefaultsPayload
}

const EMPTY_DEFAULTS: RenderDefaultsPayload = {
  aspect_ratio: null,
  preset: null,
  voice_provider: null,
  voice_id: null,
  subtitle_style: null,
  llm_provider: null,
}

export async function getRenderDefaults(): Promise<RenderDefaultsEnvelope> {
  return apiFetch<RenderDefaultsEnvelope>('/api/settings/render-defaults')
}

export async function putRenderDefaults(
  defaults: Partial<RenderDefaultsPayload>,
): Promise<RenderDefaultsEnvelope> {
  return apiFetch<RenderDefaultsEnvelope>('/api/settings/render-defaults', {
    method: 'PUT',
    body: JSON.stringify(defaults),
  })
}

export async function clearRenderDefaults(): Promise<RenderDefaultsEnvelope> {
  return apiFetch<RenderDefaultsEnvelope>('/api/settings/render-defaults', {
    method: 'PUT',
    body: JSON.stringify({}),
  })
}

export { EMPTY_DEFAULTS }
