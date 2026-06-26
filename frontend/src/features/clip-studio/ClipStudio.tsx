import { useState, useEffect } from 'react'
import './ClipStudio.css'
import { RenderWorkflow } from './render/RenderWorkflow'
import { DownloadTab } from './download/DownloadTab'
import { ThemeToggle } from '../../components/ui/ThemeToggle'
import { ActiveJobBadge } from './ActiveJobBadge'
import { useUIStore } from '../../stores/uiStore'
import { useSystemResources } from '../../hooks/useSystemResources'
import { NotificationCenter } from '../../components/NotificationCenter'

// S2.6 — collapsed the in-Studio History tab; the sidebar Library is now
// the single canonical jobs/history surface. HistoryTab.tsx remains in
// the codebase as a viable component but is no longer mounted here.
type Tab = 'render' | 'download'
export type Lang = 'EN' | 'VI'

const SettingsIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

// S4.2 — map a 0–100 percentage to a status-bar dot tone. Threshold
// matches what the design tokens already imply: under 80 % is healthy
// (green), 80–95 % is warning (yellow), above 95 % is critical (red).
// null collapses to 'off' so the dot grays out instead of disappearing.
function loadTone(pct: number | null): 'ok' | 'warn' | 'fail' | 'off' {
  if (pct === null) return 'off'
  if (pct >= 95) return 'fail'
  if (pct >= 80) return 'warn'
  return 'ok'
}

function ResourceDot({
  label, pct, suffix,
}: {
  label: string; pct: number | null; suffix?: string
}) {
  const tone = loadTone(pct)
  const text = pct === null ? label : `${label} ${Math.round(pct)}%${suffix ?? ''}`
  return (
    <span className="cs-sb" title={pct === null ? `${label}: unavailable` : text}>
      <span className={`cs-sb-dot ${tone}`} />
      {text}
    </span>
  )
}

export function ClipStudio() {
  const [activeTab, setActiveTab] = useState<Tab>('render')
  // Pha 1.2 — language is sourced from the single global uiStore.lang
  // ('en' | 'vi') instead of component-local state, so the EN/VI toggle
  // here drives the whole app (dock, palette, notifications) in lockstep.
  // RenderWorkflow + render/i18n.ts still speak 'EN' | 'VI', so map across.
  const uiLang = useUIStore((s) => s.lang)
  const setUiLang = useUIStore((s) => s.setLang)
  const lang: Lang = uiLang === 'vi' ? 'VI' : 'EN'
  // N4 (audit 2026-06-15): Settings gear icon was previously a dead button
  // with no onClick. Wire it to switch the global active panel to
  // 'settings' so AppShell takes over and renders SettingsScreen.
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const { snapshot: sysSnap } = useSystemResources()

  // Pha 1.1 — when a finished download is sent to Render, flip to the
  // Render tab so the user lands where the source was just pre-filled.
  // RenderWorkflow owns consuming + clearing sendToRenderSourcePath.
  const sendToRenderSourcePath = useUIStore((s) => s.sendToRenderSourcePath)
  useEffect(() => {
    if (sendToRenderSourcePath) setActiveTab('render')
  }, [sendToRenderSourcePath])

  return (
    <div className="cs-root">
      {/* Topbar */}
      <header className="cs-topbar">
        <span className="cs-brand">
          <span className="cs-brand-mark">✦</span>
          AI Clip Studio
        </span>

        <nav className="cs-nav">
          <button
            className={`cs-nav-tab${activeTab === 'render' ? ' active' : ''}`}
            onClick={() => setActiveTab('render')}
          >
            Render
          </button>
          <button
            className={`cs-nav-tab${activeTab === 'download' ? ' active' : ''}`}
            onClick={() => setActiveTab('download')}
          >
            Download
          </button>
        </nav>

        <div className="cs-topbar-right">
          <ActiveJobBadge onClick={() => setActiveTab('render')} />
          <NotificationCenter />
          <ThemeToggle size="sm" />
          <div className="cs-lang-sw">
            <button className={`cs-lang-btn${lang === 'EN' ? ' active' : ''}`} onClick={() => setUiLang('en')}>EN</button>
            <button className={`cs-lang-btn${lang === 'VI' ? ' active' : ''}`} onClick={() => setUiLang('vi')}>VI</button>
          </div>
          <button
            className="cs-top-icon"
            title="Settings"
            onClick={() => setActivePanel('settings')}
          >
            <SettingsIcon />
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="cs-content">
        <div className={`cs-tab-pane${activeTab === 'render'   ? ' active' : ''}`}>
          <RenderWorkflow lang={lang} />
        </div>
        <div className={`cs-tab-pane${activeTab === 'download' ? ' active' : ''}`}>
          <DownloadTab lang={lang} />
        </div>
      </div>

      {/* Status bar */}
      <footer className="cs-sbar">
        <span className="cs-sb"><span className="cs-sb-dot ok" />API</span>
        <span className="cs-sb"><span className="cs-sb-dot ok" />FFmpeg</span>
        <span className="cs-sb"><span className="cs-sb-dot ok" />Whisper</span>
        <ResourceDot label="CPU" pct={sysSnap?.cpu_percent ?? null} />
        <ResourceDot
          label={sysSnap?.gpu_name ? 'GPU' : 'GPU'}
          pct={sysSnap?.gpu_percent ?? null}
        />
        <ResourceDot label="RAM" pct={sysSnap?.ram_percent ?? null} />
        <span className="cs-sb-endpoint">http://127.0.0.1:8000</span>
      </footer>
    </div>
  )
}
