/**
 * presetMapping — translate a backend preset's snake_case params into a
 * ConfigState patch (F2).
 *
 * Only the FE-facing preset params are mapped here. BE-only params (the
 * ai_clip_* range fields) have no ConfigState field and are applied
 * server-side by routers/lifecycle._apply_render_preset using the
 * render_preset_id the FE sends. Unknown keys are ignored, so a future
 * preset param that the FE doesn't surface degrades gracefully.
 */
import type { ConfigState } from './types'

// backend param (snake_case) → ConfigState key (camelCase).
const KEY_MAP: Record<string, keyof ConfigState> = {
  output_count: 'outputCount',
  target_platform: 'platform',
  target_duration: 'targetDuration',
  video_type: 'videoType',
  hook_strength: 'hookStrength',
  add_subtitle: 'subEnabled',
  subtitle_style: 'subStyle',
  llm_enabled: 'llmEnabled',
  ai_provider: 'aiProvider',
}

export function presetParamsToConfigPatch(
  params: Record<string, unknown>,
): Partial<ConfigState> {
  const patch: Partial<ConfigState> = {}
  for (const [rawKey, value] of Object.entries(params ?? {})) {
    const key = KEY_MAP[rawKey]
    if (key === undefined || value === undefined || value === null) continue
    // The backend validates preset params against PRESET_ALLOWED_PARAMS, so
    // the value type already matches the ConfigState field. Assign through a
    // string-indexed view to satisfy the heterogeneous ConfigState union.
    ;(patch as Record<string, unknown>)[key] = value
  }
  return patch
}
