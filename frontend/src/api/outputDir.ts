/**
 * Default output folder — persisted setting consumed by /api/render/process
 * when the request payload's output_dir is empty.
 *
 * Endpoint surface: /api/settings/output-dir (GET + PUT). Backend stores
 * in creator_prefs.prefs_json nested under "output_dir" (see
 * db/creator_repo.py:upsert_default_output_dir).
 *
 * Added 2026-06-15 — the backend endpoints existed since Sprint 3 but
 * there was no FE wrapper, so the SettingsScreen had no way to surface
 * a "Default output folder" form.
 */
import { apiFetch } from './client'

export interface DefaultOutputDirEnvelope {
  is_configured: boolean
  path: string | null
}

export async function getDefaultOutputDir(): Promise<DefaultOutputDirEnvelope> {
  return apiFetch<DefaultOutputDirEnvelope>('/api/settings/output-dir')
}

export async function putDefaultOutputDir(path: string | null): Promise<DefaultOutputDirEnvelope> {
  return apiFetch<DefaultOutputDirEnvelope>('/api/settings/output-dir', {
    method: 'PUT',
    body: JSON.stringify({ path }),
  })
}
