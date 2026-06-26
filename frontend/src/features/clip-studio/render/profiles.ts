/**
 * Render profiles — named snapshots of the Configure-step settings.
 *
 * Pha 2 (Render Profiles). A creator running many videos a week was
 * re-picking the same Configure options every render (only `aiProvider`
 * was remembered, in localStorage). A profile captures the whole
 * ConfigState so a one-click apply restores a known-good setup.
 *
 * Storage: localStorage only (LOW-risk, no backend, no schema migration).
 * The 3 built-ins (TikTok / Reels / Shorts) are code-defined and always
 * present; user profiles live under LS_KEY. A later phase can promote
 * persistence to creator_prefs without changing this module's surface.
 *
 * Excluded from a profile: machine-/source-specific fields (output dir,
 * manual voice text, per-clip time ranges, uploaded asset paths) — a
 * profile is a *style/option* preset, not a per-job binding.
 */
import type { ConfigState } from './types'

export interface RenderProfile {
  id: string
  name: string
  /** Built-ins are code-defined, always present, and cannot be deleted. */
  builtin?: boolean
  /** Partial ConfigState patch applied over the current cfg on apply. */
  cfg: Partial<ConfigState>
}

const LS_KEY = 'rw_render_profiles_v1'

// Fields a profile must NOT carry — they bind to a specific machine,
// source file, or one-off job rather than to a reusable style choice.
const EXCLUDED_KEYS: ReadonlyArray<keyof ConfigState> = [
  'outputDir',
  'voiceText',
  'clipLock',
  'clipExclude',
  'assetLogoPath',
  'assetIntroPath',
  'assetOutroPath',
]

/** Strip machine/source-specific fields so the snapshot is portable. */
export function profileFromConfig(cfg: ConfigState): Partial<ConfigState> {
  const out: Partial<ConfigState> = { ...cfg }
  for (const k of EXCLUDED_KEYS) delete out[k]
  return out
}

// Built-in starter profiles. Vertical 9:16 across the board; they differ
// by platform + subtitle style + AI intent so the three feel distinct.
export const BUILTIN_PROFILES: RenderProfile[] = [
  {
    id: 'builtin-tiktok',
    name: 'TikTok',
    builtin: true,
    cfg: {
      platform: 'tiktok', ratio: 'r916',
      subEnabled: true, subStyle: 'opus_pop', subHighlight: true,
      videoType: 'viral', hookStrength: 'aggressive',
    },
  },
  {
    id: 'builtin-reels',
    name: 'Reels',
    builtin: true,
    cfg: {
      platform: 'instagram_reels', ratio: 'r916',
      subEnabled: true, subStyle: 'smooth_premiere', subHighlight: true,
      videoType: 'storytelling', hookStrength: 'balanced',
    },
  },
  {
    id: 'builtin-shorts',
    name: 'Shorts',
    builtin: true,
    cfg: {
      platform: 'youtube_shorts', ratio: 'r916',
      subEnabled: true, subStyle: 'capcut_box', subHighlight: true,
      videoType: 'high_retention', hookStrength: 'balanced',
    },
  },
]

function loadUserProfiles(): RenderProfile[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // Defensive validation — drop malformed entries instead of throwing.
    return parsed.filter(
      (p): p is RenderProfile =>
        p && typeof p.id === 'string' && typeof p.name === 'string' && typeof p.cfg === 'object' && p.cfg !== null,
    )
  } catch {
    return []
  }
}

function saveUserProfiles(list: RenderProfile[]): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(list))
  } catch {
    // localStorage quota or disabled — silently drop (non-critical).
  }
}

/** Built-ins first, then user-saved profiles (newest last). */
export function listProfiles(): RenderProfile[] {
  return [...BUILTIN_PROFILES, ...loadUserProfiles()]
}

/** Persist the current cfg under `name`. Returns the created profile. */
export function saveProfile(name: string, cfg: ConfigState): RenderProfile {
  const profile: RenderProfile = {
    id: `p_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    name: name.trim() || 'Untitled',
    cfg: profileFromConfig(cfg),
  }
  saveUserProfiles([...loadUserProfiles(), profile])
  return profile
}

/** Remove a user profile by id. Built-ins are ignored (cannot be deleted). */
export function deleteProfile(id: string): void {
  saveUserProfiles(loadUserProfiles().filter((p) => p.id !== id))
}
