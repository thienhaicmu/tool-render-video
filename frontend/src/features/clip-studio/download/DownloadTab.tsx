import { useState, useEffect, useRef, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import {
  listJobs, startDownload, cancelJob, getVideoInfo,
  platformLabel, platformColor, formatFilesize,
} from '@/api/platformDownloader'
import type { DownloadJob } from '@/api/platformDownloader'
import { getDefaultOutputDir, putDefaultOutputDir } from '@/api/outputDir'
import './DownloadTab.css'

// Instant client-side platform guess from the URL host (replaced by the real
// platform from getVideoInfo once it resolves).
function guessPlatform(u: string): string {
  let h = ''
  try { h = new URL(u).hostname.toLowerCase() } catch { return 'other' }
  if (/youtube|youtu\.be/.test(h)) return 'youtube'
  if (/tiktok/.test(h)) return 'tiktok'
  if (/instagr/.test(h)) return 'instagram'
  if (/facebook|fb\.watch/.test(h)) return 'facebook'
  if (/twitter|x\.com|t\.co/.test(h)) return 'twitter'
  if (/bilibili|b23/.test(h)) return 'bilibili'
  if (/reddit|redd\.it/.test(h)) return 'reddit'
  if (/vimeo/.test(h)) return 'vimeo'
  if (/dailymotion/.test(h)) return 'dailymotion'
  if (/twitch/.test(h)) return 'twitch'
  return 'other'
}

const POLL_MS = 1500
const LS_DIR_KEY = 'dl_output_dir'

const PLATFORM_FULL: Record<string, string> = {
  youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram',
  facebook: 'Facebook', twitter: 'X (Twitter)', bilibili: 'Bilibili',
  reddit: 'Reddit', vimeo: 'Vimeo', dailymotion: 'Dailymotion', twitch: 'Twitch',
}

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

function fmtDuration(sec?: number): string {
  if (!sec || sec <= 0) return ''
  const s = Math.round(sec)
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) { const h = Math.floor(m / 60); return `${h}:${String(m % 60).padStart(2, '0')}:${String(r).padStart(2, '0')}` }
  return `${m}:${String(r).padStart(2, '0')}`
}

function qualityOpts(heights: number[]): { value: string; label: string }[] {
  const opts = [{ value: 'best', label: 'Best' }]
  const hs = (heights.length ? [...new Set(heights)] : [1080, 720, 480]).filter(h => h > 0).sort((a, b) => b - a)
  for (const h of hs) opts.push({ value: `${h}p`, label: `${h}p` })
  return opts
}

interface StagedItem {
  key: string
  url: string
  platform: string
  title?: string
  durationSec?: number
  thumbnail?: string
  heights: number[]
  quality: string
  state: 'loading' | 'ok' | 'error'
}

let _keySeq = 0
const nextKey = () => `s${Date.now()}_${_keySeq++}`

/* ── Active download card (in-progress / done / failed) ───────────────────── */
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
          <div className="dlt-badge" style={{ background: `${pColor}18`, border: `1px solid ${pColor}33`, color: pColor }} title={pFull}>{pLabel}</div>
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
            {job.output_dir && <button className="dlt-row-btn" title="Open folder" onClick={() => window.electronAPI?.openPath?.(job.output_dir)}>Open folder</button>}
            {job.output_path && <button className="dlt-row-btn" title="Copy path" onClick={() => { navigator.clipboard.writeText(job.output_path).catch(() => {}) }}>Copy path</button>}
          </div>
        )}
        {isFailed && <div className="dlt-fail-msg">⚠ {job.error_msg || 'Download failed'}</div>}
      </div>
    </div>
  )
}

function EmptyStage() {
  const chips = [
    { n: 'YouTube', c: '#ff0000' }, { n: 'TikTok', c: '#000' },
    { n: 'Instagram', c: '#e1306c' }, { n: 'Facebook', c: '#1877f2' },
    { n: 'Bilibili', c: '#00a1d6' }, { n: 'Vimeo', c: '#1ab7ea' },
    { n: 'Twitch', c: '#9146ff' }, { n: 'Reddit', c: '#ff4500' },
  ]
  const steps = [
    { t: 'Add links', s: 'Paste one or many URLs into the bar above and click Add.' },
    { t: 'Pick quality', s: 'Choose a resolution per video — or leave it on Best.' },
    { t: 'Download', s: 'Set a folder, then download the whole list at once.' },
  ]
  return (
    <div className="dlt-empty">
      <div className="dlt-empty-icon" aria-hidden="true">
        <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 10l5 5 5-5" /><path d="M12 15V3" />
        </svg>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
        <div className="dlt-empty-title">Build your download list</div>
        <div className="dlt-empty-sub">Grab videos from YouTube, TikTok, Instagram, Facebook and 10+ more — one at a time or in bulk.</div>
      </div>
      <div className="dlt-steps">
        {steps.map((s, i) => (
          <div key={s.t} className="dlt-step">
            <span className="num">{i + 1}</span>
            <span className="st-title">{s.t}</span>
            <span className="st-sub">{s.s}</span>
          </div>
        ))}
      </div>
      <div className="dlt-chips">
        {chips.map(p => <span key={p.n} className="dlt-chip"><span className="dot" style={{ background: p.c }} />{p.n}</span>)}
      </div>
    </div>
  )
}

type CookieStatus = { present: boolean; age_seconds?: number; cookie_count?: number; has_v20_warning?: boolean; detail?: string }

export function DownloadTab({ lang: _lang }: { lang: Lang }) {
  const [url, setUrl] = useState('')
  const [staged, setStaged] = useState<StagedItem[]>([])
  const [outputDir, setOutputDir] = useState('')
  const [folderInvalid, setFolderInvalid] = useState(false)
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null)
  const [cookieAction, setCookieAction] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle')
  const [showCookiePanel, setShowCookiePanel] = useState(false)
  const [showCookieHelp, setShowCookieHelp] = useState(false)
  const [cookiePath, setCookiePath] = useState('')
  const [cookieError, setCookieError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const autoPasted = useRef(false)

  const fetchCookieStatus = useCallback(async () => {
    try { setCookieStatus(await (await fetch('/api/downloader/cookie-status')).json()) } catch { /* ignore */ }
  }, [])
  const refresh = useCallback(async () => {
    try { setJobs(await listJobs(50)) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    (async () => {
      try { const env = await getDefaultOutputDir(); if (env.is_configured && env.path) { setOutputDir(env.path); return } } catch { /* ignore */ }
      const ls = localStorage.getItem(LS_DIR_KEY); if (ls) setOutputDir(ls)
    })()
  }, [])

  useEffect(() => {
    refresh(); fetchCookieStatus()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [refresh, fetchCookieStatus])

  // Enrich a staged item with title/duration/available heights (best-effort).
  const fetchInfo = useCallback(async (key: string, link: string) => {
    try {
      const info = await getVideoInfo(link)
      const heights = (info.formats || []).map(f => f.height).filter(h => h > 0)
      setStaged(prev => prev.map(it => it.key === key
        ? { ...it, title: info.title || it.title, durationSec: info.duration, thumbnail: info.thumbnail || it.thumbnail, heights, platform: info.platform || it.platform, state: 'ok' }
        : it))
    } catch {
      setStaged(prev => prev.map(it => it.key === key ? { ...it, state: 'error' } : it))
    }
  }, [])

  // Add one or more URLs (whitespace/newline separated) to the staging list.
  const addUrls = useCallback((raw: string) => {
    const links = raw.split(/[\s\n]+/).map(s => s.trim()).filter(s => s.startsWith('http'))
    if (links.length === 0) { setError('Enter a valid http(s) URL'); return }
    setError(null)
    setStaged(prev => {
      const existing = new Set(prev.map(p => p.url))
      const additions: StagedItem[] = []
      for (const link of links) {
        if (existing.has(link)) continue
        existing.add(link)
        const item: StagedItem = { key: nextKey(), url: link, platform: guessPlatform(link), quality: 'best', heights: [], state: 'loading' }
        additions.push(item)
        // Enrich title/duration/heights/platform asynchronously.
        fetchInfo(item.key, link)
      }
      return [...prev, ...additions]
    })
    setUrl('')
  }, [fetchInfo])

  const handleAdd = () => { const v = url.trim(); if (v) addUrls(v) }

  // Auto-paste on first focus of an empty input ("click → link tự vào thanh").
  const handleFocus = async () => {
    if (url || autoPasted.current) return
    autoPasted.current = true
    try { const t = await navigator.clipboard.readText(); if (t && t.trim().startsWith('http')) setUrl(t.trim()) } catch { /* ignore */ }
  }
  const handlePaste = async () => {
    try { const t = await navigator.clipboard.readText(); if (t.trim().startsWith('http')) addUrls(t) } catch { /* ignore */ }
  }

  const setQuality = (key: string, q: string) => setStaged(prev => prev.map(it => it.key === key ? { ...it, quality: q } : it))
  const removeItem = (key: string) => setStaged(prev => prev.filter(it => it.key !== key))
  const clearStaged = () => { setStaged([]); setError(null) }

  const pickDir = async () => {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) {
      setOutputDir(dir); setFolderInvalid(false); setError(null)
      localStorage.setItem(LS_DIR_KEY, dir)
      putDefaultOutputDir(dir).catch(() => {})
    }
  }

  // Validate folder, then kick off one download per staged item with its own
  // quality. Items move into the active downloads list (backend jobs).
  const handleDownloadAll = async () => {
    if (downloading || staged.length === 0) return
    if (!outputDir.trim()) { setFolderInvalid(true); setError('Choose a folder to save downloads to'); return }
    setDownloading(true); setError(null)
    const items = [...staged]
    const results = await Promise.allSettled(
      items.map(it => startDownload(it.url, outputDir.trim(), it.quality)),
    )
    const failed = results.filter(r => r.status === 'rejected').length
    // Drop the ones that started; keep any that failed to submit so the user
    // can retry them.
    const okUrls = new Set(items.filter((_, i) => results[i].status === 'fulfilled').map(it => it.url))
    setStaged(prev => prev.filter(it => !okUrls.has(it.url)))
    if (failed > 0) setError(`${failed} link(s) could not be started — check the URL or cookies.`)
    setDownloading(false)
    await refresh()
  }

  const handleAutoExtract = async () => {
    if (cookieAction === 'loading') return
    setCookieAction('loading')
    try {
      const data = await (await fetch('/api/downloader/refresh-cookies', { method: 'POST' })).json()
      setCookieStatus(data); setCookieAction(data.ok ? 'ok' : 'fail')
    } catch { setCookieAction('fail') } finally { setTimeout(() => setCookieAction('idle'), 3000) }
  }
  const handleBrowseCookies = async () => { const fp = await window.electronAPI?.pickCookiesFile?.(); if (fp) setCookiePath(fp) }
  const handleImportFile = async () => {
    const p = cookiePath.trim(); if (!p || cookieAction === 'loading') return
    setCookieAction('loading'); setCookieError(null)
    try {
      const res = await fetch('/api/downloader/import-cookies', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: p }) })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Import failed')
      setCookieStatus(data); setCookieAction('ok'); setCookiePath('')
    } catch (e) { setCookieError(e instanceof Error ? e.message : 'Import failed'); setCookieAction('fail') }
    finally { setTimeout(() => setCookieAction('idle'), 3000) }
  }

  const activeCount = jobs.filter(j => j.status === 'downloading').length
  const doneCount = jobs.filter(j => j.status === 'done').length
  const failedCount = jobs.filter(j => j.status === 'failed').length
  const queuedCount = jobs.filter(j => j.status === 'queued').length
  const inputValid = url.trim().startsWith('http')
  const cookieChipClass = cookieStatus === null ? '' : !cookieStatus.present ? 'is-missing' : cookieStatus.has_v20_warning ? 'is-warn' : 'is-ok'

  return (
    <div className="dlt">
      <div className="dlt-header">
        <div className="dlt-head-row">
          <span className="dlt-logo">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v13" /><path d="M7 11l5 5 5-5" /><path d="M5 21h14" /></svg>
          </span>
          <div className="dlt-titles">
            <span className="dlt-title">Downloader</span>
            <span className="dlt-subtitle">Add links to the list, pick quality, then download</span>
          </div>
          <button className={`dlt-cookie-chip ${cookieChipClass}`} onClick={() => setShowCookiePanel(p => !p)} title="YouTube cookie settings">
            <span>{cookieStatus?.present ? (cookieStatus.has_v20_warning ? '⚠' : '✓') : '✗'}</span>
            <span>{cookieStatus === null ? 'Cookies…' : cookieStatus.present ? `${cookieStatus.cookie_count ?? '?'} cookies${cookieStatus.has_v20_warning ? ' (v20!)' : ''}` : 'No cookies'}</span>
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
                {cookieStatus?.present ? `✓ ${cookieStatus.cookie_count} cookies${cookieStatus.age_seconds != null ? ` · ${Math.round(cookieStatus.age_seconds / 60)}m ago` : ''}` : '✗ No cookies · YouTube auth will fail'}
              </span>
              <button className={`dlt-mini-btn${cookieAction === 'ok' ? ' is-ok' : cookieAction === 'fail' ? ' is-fail' : ''}`} onClick={handleAutoExtract} disabled={cookieAction === 'loading'} title="Auto-extract from Chrome DB (Chrome ≤126)">
                {cookieAction === 'loading' ? '⟳ …' : cookieAction === 'ok' ? '✓ Done' : '⟳ Auto-extract'}
              </button>
              <button className="dlt-mini-btn" onClick={() => setShowCookieHelp(h => !h)} title="How to export from Chrome 127+" style={{ width: 26, padding: 0 }}>?</button>
            </div>
            <div className="dlt-cookie-row" style={{ paddingTop: 0 }}>
              <input className={`dlt-cookie-input${cookieError ? ' is-invalid' : ''}`} value={cookiePath} onChange={e => { setCookiePath(e.target.value); setCookieError(null) }} placeholder="Paste path to cookies.txt, or click Browse" />
              <button className="dlt-mini-btn" onClick={handleBrowseCookies} title="Browse for cookies.txt">📂 Browse</button>
              <button className="dlt-mini-btn" onClick={handleImportFile} disabled={!cookiePath.trim() || cookieAction === 'loading'} style={{ color: cookiePath.trim() ? 'var(--accent)' : undefined, borderColor: cookiePath.trim() ? 'rgba(var(--accent-rgb),.4)' : undefined }}>
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

        {/* Add bar */}
        <div className="dlt-composer" style={{ marginTop: 12 }}>
          <div className="dlt-url-row">
            <input
              className="dlt-url-input"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setError(null) }}
              onFocus={handleFocus}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="Paste one or more links (YouTube, TikTok, Instagram, Facebook…)"
            />
            {!url && <button className="dlt-icon-btn" onClick={handlePaste} title="Paste from clipboard">📋</button>}
            {url && <button className="dlt-icon-btn" onClick={() => { setUrl(''); setError(null) }} title="Clear">×</button>}
            <button className="dlt-add-btn" onClick={handleAdd} disabled={!inputValid}>+ Add to list</button>
          </div>
        </div>

        {error && <div className="dlt-error">⚠ {error}</div>}
      </div>

      {/* Body: staging list + active downloads */}
      <div className="dlt-queue">
        {staged.length === 0 && jobs.length === 0 && <EmptyStage />}

        {staged.length > 0 && (
          <>
            <div className="dlt-section-label">
              To download <span className="count">{staged.length}</span>
              <span className="spacer" />
              <button className="dlt-link-clear" onClick={clearStaged}>Clear list</button>
            </div>
            {staged.map(it => {
              const pColor = platformColor(it.platform)
              const pLabel = platformLabel(it.platform)
              const opts = qualityOpts(it.heights)
              const durTag = fmtDuration(it.durationSec)
              return (
                <div key={it.key} className={`dlt-stage-item${it.state === 'error' ? ' is-error' : ''}`}>
                  <div className="dlt-thumb" title={PLATFORM_FULL[it.platform] || it.platform}>
                    <div className="dlt-badge" style={{ background: `${pColor}22`, color: pColor }}>{pLabel}</div>
                    {it.thumbnail && <img src={it.thumbnail} alt="" loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />}
                    {durTag && <span className="dur-tag">{durTag}</span>}
                  </div>
                  <div className="dlt-stage-info">
                    <div className="dlt-stage-title">
                      {it.state === 'loading' && !it.title ? <span className="skel" /> : (it.title || it.url)}
                    </div>
                    <div className="dlt-stage-sub">
                      {it.state === 'error' && <span style={{ color: 'var(--fail)' }}>⚠ couldn't read info — will still try</span>}
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.url}</span>
                    </div>
                  </div>
                  <select className="dlt-qsel" value={it.quality} onChange={e => setQuality(it.key, e.target.value)} title="Quality for this video">
                    {opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <button className="dlt-stage-remove" onClick={() => removeItem(it.key)} title="Remove">×</button>
                </div>
              )
            })}
          </>
        )}

        {jobs.length > 0 && (
          <>
            <div className="dlt-section-label" style={{ marginTop: staged.length > 0 ? 10 : 0 }}>
              Downloads <span className="count">{jobs.length}</span>
            </div>
            {jobs.map(job => <DownloadCard key={job.id} job={job} onCancel={cancelJob} />)}
          </>
        )}
      </div>

      {/* Action bar — folder picker (validated) + Download */}
      {staged.length > 0 && (
        <div className="dlt-actionbar">
          <div className="dlt-folder-opt">
            <span className="dlt-opt-label">Save to</span>
            <div className={`dlt-folder${folderInvalid ? ' is-invalid' : ''}`} onClick={pickDir} title={outputDir || 'Choose a folder'}>
              <span style={{ flexShrink: 0 }}>📁</span>
              <span className={`dlt-folder-path${outputDir ? '' : ' is-empty'}`}>{outputDir ? '‪' + outputDir + '‬' : 'Click to choose a folder…'}</span>
              <span className="dlt-folder-change">{outputDir ? 'Change' : 'Choose'}</span>
            </div>
          </div>
          <button className="dlt-dl-btn" onClick={handleDownloadAll} disabled={downloading}>
            {downloading ? <span className="dlt-spin">⟳</span> : '↓'}
            {downloading ? 'Starting…' : `Download ${staged.length} video${staged.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}
    </div>
  )
}
