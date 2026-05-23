/**
 * App — root component, wraps AppShell with active panel routing.
 */
import { AppShell } from './layouts/AppShell'
import { useUIStore } from './stores/uiStore'
import { RenderSetupScreen } from './features/render/RenderSetupScreen'
import { HistoryScreen } from './features/jobs/HistoryScreen'
function EditorPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Editor panel — Phase 6.1</div>
}
function SettingsPanel() {
  return <div style={{ padding: 'var(--space-6)', color: 'var(--color-text-secondary)' }}>Settings panel — Phase 6.1</div>
}

const PANEL_MAP = {
  render: RenderSetupScreen,
  history: HistoryScreen,
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
