import { useState, useEffect } from 'react'
import './ClipStudio.css'
import { RenderWorkflow } from './render/RenderWorkflow'
import { DownloadTab } from './download/DownloadTab'
import { InterruptedJobsBanner } from './InterruptedJobsBanner'
import { useUIStore } from '../../stores/uiStore'
import { useSystemResources } from '../../hooks/useSystemResources'
import { useBackendHealth } from '../../hooks/useBackendHealth'

// S2.6 — collapsed the in-Studio History tab; the sidebar Library is now
// the single canonical jobs/history surface. HistoryTab.tsx remains in
// the codebase as a viable component but is no longer mounted here.
type Tab = 'render' | 'download'
export type Lang = 'EN' | 'VI'

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

// P0.1 — health dot (API reachability, Whisper warmup). Previously these
// dots were hardcoded always-green; now they reflect useBackendHealth.
function HealthDot({ label, tone, title }: {
  label: string; tone: 'ok' | 'warn' | 'fail' | 'off'; title?: string
}) {
  return (
    <span className="cs-sb" title={title ?? label}>
      <span className={`cs-sb-dot ${tone}`} />
      {label}
    </span>
  )
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
  // ('en' | 'vi'). The EN/VI toggle lives in the shared Topbar (P2.1).
  // RenderWorkflow + render/i18n.ts still speak 'EN' | 'VI', so map across.
  const uiLang = useUIStore((s) => s.lang)
  const lang: Lang = uiLang === 'vi' ? 'VI' : 'EN'
  const { snapshot: sysSnap } = useSystemResources()
  // P0.1 — real backend health for the status-bar dots (was hardcoded green).
  const { apiOk, whisperReady, warmupStatus } = useBackendHealth()

  // Pha 1.1 — when a finished download is sent to Render, flip to the
  // Render tab so the user lands where the source was just pre-filled.
  // RenderWorkflow owns consuming + clearing sendToRenderSourcePath.
  const sendToRenderSourcePath = useUIStore((s) => s.sendToRenderSourcePath)
  useEffect(() => {
    if (sendToRenderSourcePath) setActiveTab('render')
  }, [sendToRenderSourcePath])

  // Pha 4 — opening a job's Monitor (from dock / drawer / notification)
  // must land on the Render tab where RenderWorkflow shows Step 3.
  const monitorJobId = useUIStore((s) => s.monitorJobId)
  useEffect(() => {
    if (monitorJobId) setActiveTab('render')
  }, [monitorJobId])

  return (
    <div className="cs-root">
      {/* P2.1 — sub-tab strip. The Studio's private topbar (brand, theme,
          lang, bell, settings gear) merged into the shared AppShell Topbar;
          only the Render/Download tabs remain Studio-local. */}
      <header className="cs-topbar">
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
      </header>

      {/* Pha 5B — one-click recovery of jobs interrupted by a restart. */}
      <InterruptedJobsBanner />

      {/* Content */}
      <div className="cs-content">
        <div className={`cs-tab-pane${activeTab === 'render'   ? ' active' : ''}`}>
          <RenderWorkflow lang={lang} />
        </div>
        <div className={`cs-tab-pane${activeTab === 'download' ? ' active' : ''}`}>
          <DownloadTab lang={lang} />
        </div>
      </div>

      {/* Status bar — P0.1: dots reflect real /health + warmup state.
          The FFmpeg dot was removed: no backend endpoint reports FFmpeg
          health, and a hardcoded green dot is worse than no dot. */}
      <footer className="cs-sbar">
        <HealthDot
          label="API"
          tone={apiOk === null ? 'off' : apiOk ? 'ok' : 'fail'}
          title={apiOk === null ? 'API: checking…' : apiOk ? 'Backend connected' : 'Backend unreachable'}
        />
        <HealthDot
          label="Whisper"
          tone={
            apiOk === false ? 'fail'
              : whisperReady === null ? 'off'
              : whisperReady ? 'ok'
              : 'warn'
          }
          title={
            apiOk === false ? 'Whisper: backend unreachable'
              : whisperReady === null ? 'Whisper: status unknown'
              : whisperReady ? `Whisper ready${warmupStatus?.model ? ` · ${warmupStatus.model}` : ''}`
              : `Whisper loading${warmupStatus?.status ? ` · ${warmupStatus.status}` : ''}`
          }
        />
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
