/**
 * Theme store — light / dark / system tri-state.
 *
 * Behavior:
 *   - 'system'  → follow OS prefers-color-scheme, react to changes live
 *   - 'light' / 'dark' → forced, ignores OS
 *   - User choice persists to localStorage under 'theme-preference'
 *   - Resolved theme is written to <html data-theme="light|dark">
 *
 * Read this file once at app startup via `initThemeStore()` (called from
 * main.tsx before React mount) so the correct theme paints on first frame
 * and there's no light/dark flash.
 */
import { create } from 'zustand'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'theme-preference'

function readStoredPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  } catch {
    /* localStorage may throw in sandboxed contexts; fall through */
  }
  return 'system'
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolve(pref: ThemePreference): ResolvedTheme {
  return pref === 'system' ? getSystemTheme() : pref
}

function applyTheme(resolved: ResolvedTheme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', resolved)
}

interface ThemeStore {
  preference: ThemePreference
  resolved: ResolvedTheme
  setPreference: (pref: ThemePreference) => void
  cyclePreference: () => void
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  preference: 'system',
  resolved: 'dark',

  setPreference: (pref) => {
    try { localStorage.setItem(STORAGE_KEY, pref) } catch { /* ignore */ }
    const resolved = resolve(pref)
    applyTheme(resolved)
    set({ preference: pref, resolved })
  },

  cyclePreference: () => {
    const order: ThemePreference[] = ['system', 'light', 'dark']
    const i = order.indexOf(get().preference)
    const next = order[(i + 1) % order.length]
    get().setPreference(next)
  },
}))

/**
 * Initialize theme on app startup. Call once from main.tsx before React mount.
 *
 * - Reads stored preference (defaults to 'system')
 * - Applies resolved theme to <html>
 * - Subscribes to OS theme changes when preference is 'system'
 */
export function initThemeStore() {
  const pref = readStoredPreference()
  const resolved = resolve(pref)
  applyTheme(resolved)
  useThemeStore.setState({ preference: pref, resolved })

  if (typeof window !== 'undefined' && window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (useThemeStore.getState().preference !== 'system') return
      const next: ResolvedTheme = mq.matches ? 'dark' : 'light'
      applyTheme(next)
      useThemeStore.setState({ resolved: next })
    }
    if (mq.addEventListener) mq.addEventListener('change', handler)
    else mq.addListener(handler)
  }
}
