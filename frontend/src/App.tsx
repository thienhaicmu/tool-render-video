/**
 * App — root component, wraps AppShell with active panel routing.
 */
import React from 'react'
import { AppShell } from './layouts/AppShell'
import { useUIStore } from './stores/uiStore'
import type { ActivePanel } from './stores/uiStore'
import { RenderSetupScreen } from './features/render/RenderSetupScreen'
import { HistoryScreen } from './features/jobs/HistoryScreen'
import { EditorScreen } from './features/editor/EditorScreen'
import { StudioScreen } from './features/studio/StudioScreen'

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
  // Canonical 5 routes (Figma-locked)
  home:     HistoryScreen,       // placeholder → HomeScreen in B6
  studio:   StudioScreen,
  library:  HistoryScreen,       // placeholder → LibraryScreen in B6+
  publish:  PublishPlaceholder,
  settings: SettingsPanel,
  // Deprecated aliases — do not add new usage
  render:   RenderSetupScreen,   // JobEmptyState navigates here
  history:  HistoryScreen,       // RenderForm/Editor navigate here
  editor:   EditorScreen,        // JobDetailDrawer navigates here
}

export function App() {
  const activePanel = useUIStore((s) => s.activePanel)
  const ActiveScreen = PANEL_MAP[activePanel]

  return (
    <AppShell>
      <ActiveScreen />
    </AppShell>
  )
}
