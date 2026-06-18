import { useState, useEffect, useRef, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import {
  listJobs, startDownload, cancelJob,
  platformLabel, platformColor, formatFilesize,
} from '@/api/platformDownloader'
import type { DownloadJob } from '@/api/platformDownloader'
import { getDefaultOutputDir, putDefaultOutputDir } from '@/api/outputDir'
import './DownloadTab.css'

const POLL_MS = 1500
const LS_DIR_KEY = 'dl_output_dir'

const PLATFORM_FULL: Record<string, string> = {
  youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram',
  facebook: 'Facebook', twitter: 'X (Twitter)', bilibili: 'Bilibili',
  reddit: 'Reddit', vimeo: 'Vimeo', dailymotion: 'Dailymotion', twitch: 'Twitch',
}

// value MUST match the backend _quality_to_format keys (best | 1080p | 720p | 480p).
const QUALITY_OPTS = [
  { value: 'best', label: 'Best' },
  { value: '1080p', label: '1080p' },
  { value: '720p', label: '720p' },
  { value: '480p', label: '480p' },
]

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued', downloading: 'Downloading', done: 'Done', failed: 'Failed',
}
const STATUS_CLASS: Record<string, string> = {
  queued: 'is-queued', downloading: 'is-active', done: 'is-done', failed: 'is-failed',
}
const statusBadgeStyle = (s: string): React.CSSProperties => {
  const map: Record<string, [string, string, string]> = {
    queued: ['rgba(var(--text-rgb),.1)', 'var(--text-2)', 'rgba(var(--text-rgb),.2)'],
    downloading: ['rgba(var(--accent-rgb),.12)', 'var(--accent)', 'rgba(var(--accent-rgb),.3)'],
    done: ['rgba(var(--ok-rgb),.12)', 'var(--ok)', 'rgba(var(--ok-rgb),.25)'],
    failed: ['rgba(var(--fail-rgb),.12)', 'var(--fail)', 'rgba(var(--fail-rgb),.25)'],
  }
  const [bg, color, border] = map[s] ?? map.queued
  return { background: bg, color, borderColor: border }
}

function DownloadCard({ job, onCancel }: { job: DownloadJob; onCancel: (id: string) => void }) {
  const pColor = platformColor(job.platform)
  const pLabel = platformLabel(job.platform)
  const pFull = PLATFORM_FULL[job.platform] || job.platform
  const isActive = job.status === 'downloading'
  const isDone = job.status === 'done'
  const isFailed = job.status === 'failed'
  const isQueued = job.status === 'queued'

  return (
    <div className={`dlt-card${isActive ? ' is-active' : ''}`}>
      {(isActive || isDone) && (
        <div className={`dlt-card-bar${isDone ? ' is-done' : ''}`}>
          <i style={{ width: `${Math.max(2, isDone ? 100 : job.progress)}%`, background: isDone ? undefined : `linear-gradient(90deg,${pColor}cc,var(--accent))` }} />
        </div>
      )}
      {isFailed && <div className="dlt-card-bar is-failed" />}

      <div className="dlt-card-body">
        <div className="dlt-card-top">
          <div className="dlt-badge" style={{ background: `${pColor}18`, border: `1px solid ${pColor}33`, color: pColor }} title={pFull}>
            {pLabel}
          </div>
          <div className="dlt-card-info">
            <div className="dlt-card-title">{job.title || job.url}</div>
            <div className="dlt-card-url">{job.url}</div>
          </div>
          <span className={`dlt-status-badge ${STATUS_CLASS[job.status] ?? ''}`} style={statusBadgeStyle(job.status)}>
            {(STATUS_LABEL[job.status] ?? job.status).toUpperCase()}
          </span>
        </div>

        {isActive && (
          <div className="dlt-progress">
            <span className="dlt-pct">{job.progress}%</span>
            <div className="dlt-progress-meta">
              {job.speed_str && <div>↑ {job.speed_str}</div>}
              {job.eta_str && <div className="eta">ETA {job.eta_str}</div>}
            </div>
            <button className="dlt-row-btn is-danger" onClick={() => onCancel(job.id)}>Cancel</button>
          </div>
        )}

        {isQueued && (
          <div className="dlt-card-foot">
            <span style={{ flex: 1, fontSize: 10, color: 'var(--text-3)' }}>Waiting in queue…</span>
            <button className="dlt-row-btn" onClick={() => onCancel(job.id)}>Cancel</button>
          </div>
        )}

        {isDone && (
          <div className="dlt-card-foot">
            <span style={{ fontSize: 18, color: 'var(--ok)' }}>✓</span>
            <div className="dlt-foot-file">
              {job.filename && <div className="name">{job.filename}</div>}
              {job.filesize > 0 && <div className="size">{formatFilesize(job.filesize)}</div>}
            </div>
            {job.output_dir && (
              <button className="dlt-row-btn" title="Open folder" onClick={() => window.electronAPI?.openPath?.(job.output_dir)}>
                Open folder
              </button>
            )}
            {job.output_path && (
              <button className="dlt-row-btn" title="Copy path" onClick={() => { navigator.clipboard.writeText(job.output_path).catch(() => {}) }}>
                Copy path
              </button>
            )}
          </div>
        )}

        {isFailed && <div className="dlt-fail-msg">⚠ {job.error_msg || 'Download failed'}</div>}
      </div>
    </div>
  )
}

function EmptyQueue() {
  const chips = [
    { n: 'YouTube', c: '#ff0000' }, { n: 'TikTok', c: '#000' },
    { n: 'Instagram', c: '#e1306c' }, { n: 'Facebook', c: '#1877f2' },
    { n: 'Bilibili', c: '#00a1d6' }, { n: 'Vimeo', c: '#1ab7ea' },
    { n: 'Twitch', c: '#9146ff' }, { n: 'Reddit', c: '#ff4500' },
  ]
  return (
    <div className="dlt-empty">
      <div className="dlt-empty-icon" aria-hidden="true">
        <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 10l5 5 5-5" /><path d="M12 15V3" />
        </svg>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
        <div className="dlt-empty-title">Paste a URL to start downloading</div>
        <div className="dlt-empty-sub">Drop in a link from YouTube, TikTok, Instagram, Facebook and 10+ more platforms — choose a folder and we'll grab it.</div>
      </div>
      <div className="dlt-chips">
        {chips.map(p => (
          <span key={p.n} className="dlt-chip"><span className="dot" style={{ background: p.c }} />{p.n}</span>
        ))}
      </div>
    </div>
  )
}

type CookieStatus = {
  present: boolean
  age_seconds?: number
  cookie_count?: number
  has_v20_warning?: boolean
  detail?: string
}

export function DownloadTab({ lang: _lang }: { lang: Lang }) {
  const [url, setUrl] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [folderInvalid, setFolderInvalid] = useState(false)
  const [quality, setQuality] = useState('best')
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null)
  const [cookieAction, setCookieAction] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle')
  const [showCookiePanel, setShowCookiePanel] = useState(false)
  const [showCookieHelp, setShowCookieHelp] = useState(false)
  const [cookiePath, setCookiePath] = useState('')
  const [cookieError, setCookieError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const fetchCookieStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/downloader/cookie-status')
      setCookieStatus(await res.json())
    } catch { /* ignore */ }
  }, [])

  const refresh = useCallback(async () => {
    try { setJobs(await listJobs(50)) } catch { /* ignore */ }
  }, [])

  // Load the saved output folder: default-output-dir setting first, then the
  // last folder used on this machine (localStorage).
  useEffect(() => {
    (async () => {
      try {
        const env = await getDefaultOutputDir()
        if (env.is_configured && env.path) { setOutputDir(env.path); return }
      } catch { /* ignore */ }
      const ls = localStorage.getItem(LS_DIR_KEY)
      if (ls) setOutputDir(ls)
    })()
  }, [])

  useEffect(() => {
    refresh()
    fetchCookieStatus()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [refresh, fetchCookieStatus])

  const pickDir = async () => {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) {
      setOutputDir(dir)
      setFolderInvalid(false)
      setError(null)
      localStorage.setItem(LS_DIR_KEY, dir)
      putDefaultOutputDir(dir).catch(() => {})  // best-effort: remember as default
    }
  }

  const handleAdd = async () => {
    const v = url.trim()
    if (!v || adding) return
    if (!v.startsWith('http')) { setError('Enter a valid http(s) URL'); return }
    // Validate the save folder BEFORE submitting — no silent 'output' default.
    if (!outputDir.trim()) {
      setFolderInvalid(true)
      setError('Choose a folder to save downloads to')
      return
    }
    setAdding(true)
    setError(null)
    try {
      await startDownload(v, outputDir.trim(), quality)
      setUrl('')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start download')
    } finally {
      setAdding(false)
    }
  }

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text.startsWith('http')) { setUrl(text); setError(null) }
    } catch { /* ignore */ }
  }

  const handleAutoExtract = async () => {
    if (cookieAction === 'loading') return
    setCookieAction('loading')
    try {
      const res = await fetch('/api/downloader/refresh-cookies', { method: 'POST' })
      const data = await res.json()
      setCookieStatus(data)
      setCookieAction(data.ok ? 'ok' : 'fail')
    } catch { setCookieAction('fail') }
    finally { setTimeout(() => setCookieAction('idle'), 3000) }
  }

  const handleBrowseCookies = async () => {
    const filePath = await window.electronAPI?.pickCookiesFile?.()
    if (filePath) setCookiePath(filePath)
  }

  const handleImportFile = async () => {
    const pathToUse = cookiePath.trim()
    if (!pathToUse || cookieAction === 'loading') return
    setCookieAction('loading')
    setCookieError(null)
    try {
      const res = await fetch('/api/downloader/import-cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathToUse }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Import failed')
      setCookieStatus(data)
      setCookieAction('ok')
      setCookiePath('')
    } catch (e) {
      setCookieError(e instanceof Error ? e.message : 'Import failed')
      setCookieAction('fail')
    } finally { setTimeout(() => setCookieAction('idle'), 3000) }
  }

  const activeCount = jobs.filter((j) => j.status === 'downloading').length
  const doneCount = jobs.filter((j) => j.status === 'done').length
  const failedCount = jobs.filter((j) => j.status === 'failed').length
  const queuedCount = jobs.filter((j) => j.status === 'queued').length
  const inputValid = url.trim().startsWith('http')

  const cookieChipClass = cookieStatus === null ? ''
    : !cookieStatus.present ? 'is-missing'
      : cookieStatus.has_v20_warning ? 'is-warn' : 'is-ok'

  return (
    <div className="dlt">
      <div className="dlt-header">
        <div className="dlt-head-row">
          <span className="dlt-logo">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v13" /><path d="M7 11l5 5 5-5" /><path d="M5 21h14" />
            </svg>
          </span>
          <div className="dlt-titles">
            <span className="dlt-title">Downloader</span>
            <span className="dlt-subtitle">Paste a link to fetch video from any platform</span>
          </div>

          <button
            className={`dlt-cookie-chip ${cookieChipClass}`}
            onClick={() => setShowCookiePanel(p => !p)}
            title="YouTube cookie settings"
          >
            <span>{cookieStatus?.present ? (cookieStatus.has_v20_warning ? '⚠' : '✓') : '✗'}</span>
            <span>
              {cookieStatus === null ? 'Cookies…'
                : cookieStatus.present
                  ? `${cookieStatus.cookie_count ?? '?'} cookies${cookieStatus.has_v20_warning ? ' (v20!)' : ''}`
                  : 'No cookies'}
            </span>
            <span style={{ opacity: 0.5, fontSize: 9 }}>{showCookiePanel ? '▲' : '▼'}</span>
          </button>

          <div className="dlt-pills">
            {activeCount > 0 && <span className="dlt-pill is-active">{activeCount} downloading</span>}
            {queuedCount > 0 && <span className="dlt-pill is-queued">{queuedCount} queued</span>}
            {doneCount > 0 && <span className="dlt-pill is-done">{doneCount} done</span>}
            {failedCount > 0 && <span className="dlt-pill is-failed">{failedCount} failed</span>}
          </div>
        </div>

        {showCookiePanel && (
          <div className="dlt-cookie-panel">
            <div className="dlt-cookie-row">
              <span className="dlt-cookie-status" style={{ color: cookieStatus?.present ? (cookieStatus.has_v20_warning ? 'var(--status-warning)' : 'var(--ok)') : 'var(--fail)' }}>
                {cookieStatus?.present
                  ? `✓ ${cookieStatus.cookie_count} cookies${cookieStatus.age_seconds != null ? ` · ${Math.round(cookieStatus.age_seconds / 60)}m ago` : ''}`
                  : '✗ No cookies · YouTube auth will fail'}
              </span>
              <button
                className={`dlt-mini-btn${cookieAction === 'ok' ? ' is-ok' : cookieAction === 'fail' ? ' is-fail' : ''}`}
                onClick={handleAutoExtract}
                disabled={cookieAction === 'loading'}
                title="Auto-extract from Chrome DB (Chrome ≤126)"
              >
                {cookieAction === 'loading' ? '⟳ …' : cookieAction === 'ok' ? '✓ Done' : '⟳ Auto-extract'}
              </button>
              <button className="dlt-mini-btn" onClick={() => setShowCookieHelp(h => !h)} title="How to export from Chrome 127+" style={{ width: 26, padding: 0 }}>?</button>
            </div>
            <div className="dlt-cookie-row" style={{ paddingTop: 0 }}>
              <input
                className={`dlt-cookie-input${cookieError ? ' is-invalid' : ''}`}
                value={cookiePath}
                onChange={e => { setCookiePath(e.target.value); setCookieError(null) }}
                placeholder="Paste path to cookies.txt, or click Browse"
              />
              <button className="dlt-mini-btn" onClick={handleBrowseCookies} title="Browse for cookies.txt">📂 Browse</button>
              <button
                className="dlt-mini-btn"
                onClick={handleImportFile}
                disabled={!cookiePath.trim() || cookieAction === 'loading'}
                style={{ color: cookiePath.trim() ? 'var(--accent)' : undefined, borderColor: cookiePath.trim() ? 'rgba(var(--accent-rgb),.4)' : undefined }}
              >
                {cookieAction === 'loading' ? '⟳ Importing…' : 'Import'}
              </button>
            </div>
            {cookieError && <div className="dlt-cookie-row" style={{ paddingTop: 0 }}><div className="dlt-fail-msg" style={{ margin: 0, flex: 1 }}>⚠ {cookieError}</div></div>}
            {showCookieHelp && (
              <div className="dlt-cookie-help">
                <ol>
                  <li>Install <strong>"Get cookies.txt LOCALLY"</strong> from the Chrome Web Store</li>
                  <li>Open <strong>youtube.com</strong> — sign in first</li>
                  <li>Click the extension → <strong>Export cookies for this tab</strong></li>
                  <li>Save the file → paste its path above → click <strong>Import</strong></li>
                </ol>
              </div>
            )}
          </div>
        )}

        {/* Composer */}
        <div className="dlt-composer" style={{ marginTop: 12 }}>
          <div className="dlt-url-row">
            <input
              ref={inputRef}
              className="dlt-url-input"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setError(null) }}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="Paste YouTube, TikTok, Instagram, Facebook URL…"
            />
            {!url && <button className="dlt-icon-btn" onClick={handlePaste} title="Paste from clipboard">📋</button>}
            {url && <button className="dlt-icon-btn" onClick={() => { setUrl(''); setError(null) }} title="Clear">×</button>}
            <button className="dlt-add-btn" onClick={handleAdd} disabled={adding || !inputValid}>
              {adding ? <span className="dlt-spin">⟳</span> : '↓'} {adding ? 'Adding…' : 'Add'}
            </button>
          </div>

          <div className="dlt-options">
            <div className="dlt-opt">
              <span className="dlt-opt-label">Quality</span>
              <div className="dlt-quality">
                {QUALITY_OPTS.map(q => (
                  <button key={q.value} className={quality === q.value ? 'is-sel' : ''} onClick={() => setQuality(q.value)}>{q.label}</button>
                ))}
              </div>
            </div>
            <div className="dlt-opt dlt-folder-opt">
              <span className="dlt-opt-label">Save to</span>
              <div className={`dlt-folder${folderInvalid ? ' is-invalid' : ''}`} onClick={pickDir} title={outputDir || 'Choose a folder'}>
                <span style={{ flexShrink: 0 }}>📁</span>
                <span className={`dlt-folder-path${outputDir ? '' : ' is-empty'}`}>
                  {outputDir ? '‪' + outputDir + '‬' : 'Click to choose a folder…'}
                </span>
                <span className="dlt-folder-change">{outputDir ? 'Change' : 'Choose'}</span>
              </div>
            </div>
          </div>
        </div>

        {error && <div className="dlt-error">⚠ {error}</div>}
      </div>

      <div className="dlt-queue">
        {jobs.length === 0 ? <EmptyQueue /> : jobs.map((job) => <DownloadCard key={job.id} job={job} onCancel={cancelJob} />)}
      </div>
    </div>
  )
}
