/**
 * App — root component, wraps AppShell with active panel routing.
 * ClipStudio panel bypasses AppShell for a full-screen experience.
 *
 * Sprint 5.6: retired features/studio/ (the older 6-step flow). All render
 * work goes through features/clip-studio/ (RenderWorkflow). The legacy
 * `studio` panel route is removed; uiStore.ActivePanel no longer accepts it.
 */
import React, { Suspense, lazy } from 'react'
import { AppShell } from './layouts/AppShell'
import { ActiveJobsDock } from './layouts/ActiveJobsDock'
import { useUIStore } from './stores/uiStore'
import type { ActivePanel } from './stores/uiStore'
import { Notifications } from './components/ui/Notifications'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { useJobCompletionNotifier } from './hooks/useJobCompletionNotifier'

// Code-split each top-level screen into its own chunk (F1). The initial
// bundle no longer carries every screen's code; a screen's chunk is fetched
// the first time its panel is opened. Named exports are mapped to default.
const importHistory    = () => import('./features/jobs/HistoryScreen').then(m => ({ default: m.HistoryScreen }))
const importEditor     = () => import('./features/editor/EditorScreen').then(m => ({ default: m.EditorScreen }))
const importDownloader = () => import('./features/downloader/DownloaderScreen').then(m => ({ default: m.DownloaderScreen }))
const importClipStudio = () => import('./features/clip-studio/ClipStudio').then(m => ({ default: m.ClipStudio }))
const importSettings   = () => import('./features/settings/SettingsScreen').then(m => ({ default: m.SettingsScreen }))

const HistoryScreen    = lazy(importHistory)
const EditorScreen     = lazy(importEditor)
const DownloaderScreen = lazy(importDownloader)
const ClipStudio       = lazy(importClipStudio)
const SettingsScreen   = lazy(importSettings)

// Warm screen chunks during browser idle so panel switches are instant (no
// Suspense flash). ClipStudio is the heaviest → prefetched first.
const PREFETCH_IMPORTS = [importClipStudio, importHistory, importDownloader, importEditor, importSettings]

function PublishPlaceholder() {
  return (
    <div style={{ padding: 'var(--space-6)', color: 'var(--text-secondary)' }}>
      Publish — coming soon
    </div>
  )
}

const PANEL_MAP: Record<ActivePanel, React.ComponentType> = {
  // Canonical routes
  home:          HistoryScreen,
  'clip-studio': ClipStudio,
  library:       HistoryScreen,
  publish:       PublishPlaceholder,
  settings:      SettingsScreen,
  download:      DownloaderScreen,
  // Deprecated aliases — do not add new usage
  render:        HistoryScreen,
  history:       HistoryScreen,
  editor:        EditorScreen,
}

const FULLSCREEN_PANELS: ActivePanel[] = ['clip-studio']

function ScreenFallback() {
  return (
    <div className="screen-fallback">
      <div className="screen-fallback__spinner" />
    </div>
  )
}

export function App() {
  const activePanel = useUIStore((s) => s.activePanel)
  const ActiveScreen = PANEL_MAP[activePanel]

  // Watch jobsStore for terminal transitions and fire OS notifications.
  useJobCompletionNotifier()

  // Prefetch all screen chunks once the browser is idle so the first open of
  // any panel is instant. Best-effort: requestIdleCallback when available,
  // else a short timeout. Failures are ignored (the lazy() import retries).
  React.useEffect(() => {
    let cancelled = false
    const warm = () => {
      if (cancelled) return
      for (const imp of PREFETCH_IMPORTS) { void imp().catch(() => {}) }
    }
    const ric = (window as unknown as {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number
    }).requestIdleCallback
    const id = ric ? ric(warm, { timeout: 2500 }) : window.setTimeout(warm, 1500)
    return () => {
      cancelled = true
      const cic = (window as unknown as { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback
      if (ric && cic) cic(id as number)
      else clearTimeout(id as number)
    }
  }, [])

  if (FULLSCREEN_PANELS.includes(activePanel)) {
    return (
      <ErrorBoundary>
        <div style={{ position: 'fixed', inset: 0, zIndex: 100 }}>
          <Suspense fallback={<ScreenFallback />}>
            <ActiveScreen />
          </Suspense>
          <ActiveJobsDock />
          <Notifications />
        </div>
      </ErrorBoundary>
    )
  }

  return (
    <ErrorBoundary>
      <AppShell>
        <Suspense fallback={<ScreenFallback />}>
          <ActiveScreen />
        </Suspense>
      </AppShell>
    </ErrorBoundary>
  )
}
