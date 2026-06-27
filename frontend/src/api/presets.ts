/**
 * Render presets API (F2). The backend owns the preset definitions
 * (built-in + user-saved) in the render_presets table; the FE fetches them
 * here — no FE-side duplication of preset bundles (avoids the FE↔BE drift
 * class C1 closed).
 */
import { apiFetch } from './client'

export interface RenderPresetDto {
  preset_id: string
  name: string
  description: string
  platform: string
  is_builtin: boolean
  params: Record<string, unknown>
}

/** List presets (optionally filtered). Returns [] on any shape surprise. */
export async function listPresets(platform = ''): Promise<RenderPresetDto[]> {
  const qs = platform ? `?platform=${encodeURIComponent(platform)}` : ''
  const res = await apiFetch<{ presets?: RenderPresetDto[] }>(`/api/presets${qs}`)
  return res.presets ?? []
}

/** Built-in presets only — the curated F2 "pick a preset" surface. */
export async function listBuiltinPresets(): Promise<RenderPresetDto[]> {
  return (await listPresets()).filter((p) => p.is_builtin)
}
