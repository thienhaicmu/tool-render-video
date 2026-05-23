/**
 * App — root component, wraps AppShell with active panel routing.
 */
import React from 'react'
import { AppShell } from './layouts/AppShell'
import { useUIStore } from './stores/uiStore'

// Lazy panel placeholders — will be replaced by real feature screens in Phase 6.1+
function RenderPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Render panel — Phase 6.1</div>
}
function HistoryPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>History panel — Phase 6.1</div>
}
function EditorPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Editor panel — Phase 6.1</div>
}
function SettingsPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Settings panel — Phase 6.1</div>
}

const PANEL_MAP = {
  render: RenderPanel,
  history: HistoryPanel,
  editor: EditorPanel,
  settings: SettingsPanel,
} as const

export function App() {
  const activePanel = useUIStore((s) => s.activePanel)
  const ActivePanel = PANEL_MAP[activePanel]

  return (
    <AppShell>
      <ActivePanel />
    </AppShell>
  )
}
