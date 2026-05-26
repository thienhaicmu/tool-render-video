import { useState } from 'react'
import './ClipStudio.css'
import { RenderWorkflow } from './render/RenderWorkflow'
import { DownloadTab } from './download/DownloadTab'
import { HistoryTab } from './history/HistoryTab'

type Tab = 'render' | 'download' | 'history'
export type Lang = 'EN' | 'VI'

const SettingsIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

export function ClipStudio() {
  const [activeTab, setActiveTab] = useState<Tab>('render')
  const [lang, setLang] = useState<Lang>('EN')

  return (
    <div className="cs-root">
      {/* Topbar */}
      <header className="cs-topbar">
        <span className="cs-brand">
          AI<span className="cs-brand-pulse" />CLIP
        </span>

        <nav className="cs-nav">
          <button
            className={`cs-nav-tab${activeTab === 'render' ? ' active' : ''}`}
            onClick={() => setActiveTab('render')}
          >
            RENDER
          </button>
          <button
            className={`cs-nav-tab${activeTab === 'download' ? ' active' : ''}`}
            onClick={() => setActiveTab('download')}
          >
            DOWNLOAD
          </button>
          <button
            className={`cs-nav-tab${activeTab === 'history' ? ' active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            HISTORY
          </button>
        </nav>

        <div className="cs-topbar-right">
          <div className="cs-lang-sw">
            <button className={`cs-lang-btn${lang === 'EN' ? ' active' : ''}`} onClick={() => setLang('EN')}>EN</button>
            <button className={`cs-lang-btn${lang === 'VI' ? ' active' : ''}`} onClick={() => setLang('VI')}>VI</button>
          </div>
          <button className="cs-top-icon" title="Settings">
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
        <div className={`cs-tab-pane${activeTab === 'history'  ? ' active' : ''}`}>
          <HistoryTab lang={lang} />
        </div>
      </div>

      {/* Status bar */}
      <footer className="cs-sbar">
        <span className="cs-sb"><span className="cs-sb-dot ok" />API</span>
        <span className="cs-sb"><span className="cs-sb-dot ok" />FFmpeg</span>
        <span className="cs-sb"><span className="cs-sb-dot ok" />Whisper</span>
        <span className="cs-sb"><span className="cs-sb-dot off" />GPU</span>
        <span className="cs-sb-endpoint">http://127.0.0.1:8000</span>
      </footer>
    </div>
  )
}
