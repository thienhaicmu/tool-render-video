/**
 * App — root component, wraps AppShell with active panel routing.
 * Studio panel bypasses AppShell for a full-screen experience.
 */
import React from 'react'
import { AppShell } from './layouts/AppShell'
import { useUIStore } from './stores/uiStore'
import type { ActivePanel } from './stores/uiStore'
import { RenderSetupScreen } from './features/render/RenderSetupScreen'
import { HistoryScreen } from './features/jobs/HistoryScreen'
import { EditorScreen } from './features/editor/EditorScreen'
import { StudioScreen } from './features/studio/StudioScreen'
import { DownloaderScreen } from './features/downloader/DownloaderScreen'
import { ClipStudio } from './features/clip-studio/ClipStudio'
import { Notifications } from './components/ui/Notifications'

function SettingsPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Settings panel — Phase 6.1</div>
}

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
  studio:        StudioScreen,
  library:       HistoryScreen,
  publish:       PublishPlaceholder,
  settings:      SettingsPanel,
  download:      DownloaderScreen,
  // Deprecated aliases — do not add new usage
  render:        RenderSetupScreen,
  history:       HistoryScreen,
  editor:        EditorScreen,
}

const FULLSCREEN_PANELS: ActivePanel[] = ['studio', 'clip-studio']

export function App() {
  const activePanel = useUIStore((s) => s.activePanel)
  const ActiveScreen = PANEL_MAP[activePanel]

  if (FULLSCREEN_PANELS.includes(activePanel)) {
    return (
      <div style={{ position: 'fixed', inset: 0, zIndex: 100 }}>
        <ActiveScreen />
        <Notifications />
      </div>
    )
  }

  return (
    <AppShell>
      <ActiveScreen />
    </AppShell>
  )
}
