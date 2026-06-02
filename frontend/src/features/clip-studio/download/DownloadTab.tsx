import { useState, useEffect, useRef, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import {
  listJobs, startDownload, cancelJob,
  platformLabel, platformColor, formatFilesize,
} from '@/api/platformDownloader'
import type { DownloadJob } from '@/api/platformDownloader'

const POLL_MS = 1500

const PLATFORM_FULL: Record<string, string> = {
  youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram',
  facebook: 'Facebook', twitter: 'X (Twitter)', bilibili: 'Bilibili',
  reddit: 'Reddit', vimeo: 'Vimeo', dailymotion: 'Dailymotion', twitch: 'Twitch',
}

const STATUS_META: Record<string, { color: string; bg: string; border: string; label: string }> = {
  queued:      { color: '#8A93B0', bg: 'rgba(138,147,176,.10)', border: 'rgba(138,147,176,.2)', label: 'Queued' },
  downloading: { color: '#7B61FF', bg: 'rgba(123,97,255,.12)',  border: 'rgba(123,97,255,.3)',  label: 'Downloading' },
  done:        { color: '#00C896', bg: 'rgba(0,200,150,.12)',   border: 'rgba(0,200,150,.25)',  label: 'Done' },
  failed:      { color: '#E8407A', bg: 'rgba(232,64,122,.12)',  border: 'rgba(232,64,122,.25)', label: 'Failed' },
}
const statusMeta = (s: string) => STATUS_META[s] ?? STATUS_META.queued

function DownloadCard({ job, onCancel }: { job: DownloadJob; onCancel: (id: string) => void }) {
  const st = statusMeta(job.status)
  const pColor = platformColor(job.platform)
  const pLabel = platformLabel(job.platform)
  const pFull  = PLATFORM_FULL[job.platform] || job.platform
  const isActive = job.status === 'downloading'
  const isDone   = job.status === 'done'
  const isFailed = job.status === 'failed'
  const isQueued = job.status === 'queued'
  const [hov, setHov] = useState(false)

  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        borderRadius: 10,
        background: hov ? '#161C2C' : '#111622',
        border: `1px solid ${isActive ? 'rgba(123,97,255,.3)' : '#1C2438'}`,
        overflow: 'hidden',
        flexShrink: 0,
        transition: 'border-color .15s, background .12s',
        boxShadow: isActive ? '0 0 0 1px rgba(123,97,255,.15)' : 'none',
      }}
    >
      {/* Progress bar at top */}
      {(isActive || isDone) && (
        <div style={{ height: 3, background: 'rgba(255,255,255,.05)', position: 'relative' as const }}>
          <div style={{
            position: 'absolute' as const, top: 0, left: 0, bottom: 0,
            width: isDone ? '100%' : `${Math.max(2, job.progress)}%`,
            background: isDone
              ? 'linear-gradient(90deg,#00C896,#00E5C8)'
              : `linear-gradient(90deg,${pColor}cc,#7B61FF)`,
            transition: 'width .5s ease',
            boxShadow: isActive ? `0 0 8px ${pColor}80` : 'none',
          }} />
        </div>
      )}
      {isFailed && <div style={{ height: 3, background: '#E8407A' }} />}
      {isQueued  && <div style={{ height: 3, background: '#1C2438' }} />}

      <div style={{ padding: '12px 14px' }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
          {/* Platform badge */}
          <div style={{
            flexShrink: 0, display: 'flex', flexDirection: 'column' as const,
            alignItems: 'center', gap: 2, width: 36,
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: `${pColor}18`, border: `1px solid ${pColor}33`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 800, color: pColor,
              letterSpacing: '-.02em',
            }}>
              {pLabel}
            </div>
            <span style={{ fontSize: 8, color: '#4A5270', textAlign: 'center' as const, whiteSpace: 'nowrap' as const }}>
              {pFull.slice(0, 7)}
            </span>
          </div>

          {/* Info */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 12, fontWeight: 600, color: '#EEF0F8',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
              marginBottom: 3,
            }}>
              {job.title || job.url}
            </div>
            <div style={{ fontSize: 10, color: '#4A5270', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
              {job.url}
            </div>
          </div>

          {/* Status badge */}
          <span style={{
            fontSize: 9, fontWeight: 800, padding: '3px 8px', borderRadius: 20,
            background: st.bg, color: st.color, border: `1px solid ${st.border}`,
            letterSpacing: '.04em', flexShrink: 0,
            animation: isActive ? 'dl-pulse 1.4s ease-in-out infinite' : 'none',
          }}>
            {st.label.toUpperCase()}
          </span>
        </div>

        {/* Progress details row */}
        {isActive && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '8px 10px', background: 'rgba(123,97,255,.06)',
            borderRadius: 8, border: '1px solid rgba(123,97,255,.12)',
          }}>
            <span style={{ fontSize: 22, fontWeight: 800, color: '#7B61FF', fontFamily: 'monospace', lineHeight: 1 }}>
              {job.progress}%
            </span>
            <div style={{ flex: 1 }}>
              {job.speed_str && (
                <div style={{ fontSize: 10, color: '#8A93B0', marginBottom: 2 }}>
                  ↑ {job.speed_str}
                </div>
              )}
              {job.eta_str && (
                <div style={{ fontSize: 10, color: '#4A5270' }}>ETA {job.eta_str}</div>
              )}
            </div>
            <button
              onClick={() => onCancel(job.id)}
              style={{
                padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
                border: '1px solid rgba(232,64,122,.3)', background: 'rgba(232,64,122,.08)',
                color: '#E8407A', fontSize: 10, fontWeight: 700,
              }}
            >
              Cancel
            </button>
          </div>
        )}

        {isQueued && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: '#4A5270' }}>Waiting in queue…</span>
            <button
              onClick={() => onCancel(job.id)}
              style={{
                marginLeft: 'auto', padding: '3px 8px', borderRadius: 5, cursor: 'pointer',
                border: '1px solid #1C2438', background: 'transparent',
                color: '#4A5270', fontSize: 10, fontWeight: 600,
              }}
            >
              Cancel
            </button>
          </div>
        )}

        {isDone && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20, color: '#00C896' }}>✓</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              {job.filename && (
                <div style={{ fontSize: 10, color: '#8A93B0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, fontFamily: 'monospace' }}>
                  {job.filename}
                </div>
              )}
              {job.filesize > 0 && (
                <div style={{ fontSize: 10, color: '#00C896', fontWeight: 700, marginTop: 2 }}>
                  {formatFilesize(job.filesize)}
                </div>
              )}
            </div>
            {job.filename && (
              <button
                onClick={() => { navigator.clipboard.writeText(job.filename).catch(() => {}) }}
                title="Copy path"
                style={{
                  padding: '4px 10px', borderRadius: 6, cursor: 'pointer', flexShrink: 0,
                  border: '1px solid #1C2438', background: 'transparent',
                  color: '#8A93B0', fontSize: 10, fontWeight: 600,
                }}
              >
                Copy path
              </button>
            )}
          </div>
        )}

        {isFailed && (
          <div style={{
            padding: '8px 10px', background: 'rgba(232,64,122,.06)',
            borderRadius: 8, border: '1px solid rgba(232,64,122,.15)',
          }}>
            <div style={{ fontSize: 10, color: '#E8407A', lineHeight: 1.5, wordBreak: 'break-word' as const }}>
              ⚠ {job.error_msg || 'Download failed'}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyQueue() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 40 }}>
      <div style={{ fontSize: 40, opacity: .15 }}>⬇</div>
      <div style={{ fontSize: 13, color: '#8A93B0', fontWeight: 600 }}>Paste a URL to start downloading</div>
      <div style={{ fontSize: 11, color: '#4A5270', textAlign: 'center' as const, lineHeight: 1.6 }}>
        YouTube · TikTok · Instagram · Facebook<br />
        Bilibili · Vimeo · Twitch · and more
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
  const [url, setUrl]               = useState('')
  const [outputDir, setOutputDir]   = useState('')
  const [quality, setQuality]       = useState('best')
  const [jobs, setJobs]             = useState<DownloadJob[]>([])
  const [adding, setAdding]         = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null)
  const [cookieAction, setCookieAction] = useState<'idle'|'loading'|'ok'|'fail'>('idle')
  const [showCookiePanel, setShowCookiePanel] = useState(false)
  const [showCookieHelp, setShowCookieHelp] = useState(false)
  const [cookiePath, setCookiePath] = useState('')
  const [cookieError, setCookieError] = useState<string | null>(null)
  const pollRef                     = useRef<ReturnType<typeof setInterval> | null>(null)
  const inputRef                    = useRef<HTMLInputElement>(null)

  const fetchCookieStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/downloader/cookie-status')
      const data = await res.json()
      setCookieStatus(data)
    } catch { /* ignore */ }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const list = await listJobs(50)
      setJobs(list)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    refresh()
    fetchCookieStatus()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [refresh, fetchCookieStatus])

  const pickDir = async () => {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setOutputDir(dir)
  }

  const handleAdd = async () => {
    const v = url.trim()
    if (!v || adding) return
    setAdding(true)
    setError(null)
    try {
      await startDownload(v, outputDir || 'output', quality)
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
    } catch {
      setCookieAction('fail')
    } finally {
      setTimeout(() => setCookieAction('idle'), 3000)
    }
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
    } finally {
      setTimeout(() => setCookieAction('idle'), 3000)
    }
  }

  const activeCount  = jobs.filter((j) => j.status === 'downloading').length
  const doneCount    = jobs.filter((j) => j.status === 'done').length
  const failedCount  = jobs.filter((j) => j.status === 'failed').length
  const queuedCount  = jobs.filter((j) => j.status === 'queued').length

  const inputValid = url.trim().startsWith('http')

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, overflow: 'hidden', background: '#090C13' }}>
      <style>{`
        @keyframes dl-pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
        @keyframes dl-spin   { to { transform: rotate(360deg) } }
      `}</style>

      {/* Header */}
      <div style={{
        padding: '14px 20px 16px',
        borderBottom: '1px solid #1C2438',
        flexShrink: 0,
        background: '#0D1019',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: showCookiePanel ? 12 : 14 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#EEF0F8', letterSpacing: '-.01em' }}>Downloader</span>

          {/* Cookie status chip */}
          <button
            onClick={() => setShowCookiePanel(p => !p)}
            title="YouTube cookie settings"
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 10px', borderRadius: 6, cursor: 'pointer', flexShrink: 0,
              border: cookieStatus?.present
                ? (cookieStatus.has_v20_warning ? '1px solid rgba(255,170,0,.3)' : '1px solid rgba(0,200,150,.3)')
                : '1px solid rgba(232,64,122,.25)',
              background: cookieStatus?.present
                ? (cookieStatus.has_v20_warning ? 'rgba(255,170,0,.08)' : 'rgba(0,200,150,.08)')
                : 'rgba(232,64,122,.08)',
              color: cookieStatus?.present
                ? (cookieStatus.has_v20_warning ? '#FFAA00' : '#00C896')
                : '#E8407A',
              fontSize: 10, fontWeight: 600, transition: 'all .15s',
            }}
          >
            <span>{cookieStatus?.present ? (cookieStatus.has_v20_warning ? '⚠' : '✓') : '✗'}</span>
            <span>
              {cookieStatus === null ? 'Cookies…'
                : cookieStatus.present
                  ? `${cookieStatus.cookie_count ?? '?'} cookies${cookieStatus.has_v20_warning ? ' (v20!)' : ''}`
                  : 'No cookies'}
            </span>
            <span style={{ opacity: .5, fontSize: 9 }}>{showCookiePanel ? '▲' : '▼'}</span>
          </button>

          <div style={{ display: 'flex', gap: 6, marginLeft: 4 }}>
            {activeCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'rgba(123,97,255,.15)', color: '#7B61FF', border: '1px solid rgba(123,97,255,.3)', animation: 'dl-pulse 1.4s infinite' }}>
                {activeCount} downloading
              </span>
            )}
            {queuedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(138,147,176,.1)', color: '#8A93B0' }}>
                {queuedCount} queued
              </span>
            )}
            {doneCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(0,200,150,.1)', color: '#00C896' }}>
                {doneCount} done
              </span>
            )}
            {failedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(232,64,122,.1)', color: '#E8407A' }}>
                {failedCount} failed
              </span>
            )}
          </div>
        </div>

        {/* Cookie panel */}
        {showCookiePanel && (
          <div style={{ marginBottom: 12, borderRadius: 8, border: '1px solid #1C2438', background: '#111622', overflow: 'hidden' }}>
            {/* Row 1: status + auto-extract + help */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px' }}>
              <span style={{ flex: 1, fontSize: 10, color: cookieStatus?.present ? (cookieStatus.has_v20_warning ? '#FFAA00' : '#00C896') : '#E8407A' }}>
                {cookieStatus?.present
                  ? `✓ ${cookieStatus.cookie_count} cookies${cookieStatus.age_seconds != null ? ` · ${Math.round(cookieStatus.age_seconds / 60)}m ago` : ''}`
                  : '✗ No cookies · YouTube auth will fail'}
              </span>
              <button
                onClick={handleAutoExtract}
                disabled={cookieAction === 'loading'}
                title="Auto-extract from Chrome DB (Chrome ≤126)"
                style={{
                  padding: '4px 10px', borderRadius: 6, flexShrink: 0,
                  border: '1px solid #2A3558', background: '#0D1019',
                  color: cookieAction === 'ok' ? '#00C896' : cookieAction === 'fail' ? '#E8407A' : '#8A93B0',
                  fontSize: 10, fontWeight: 600, cursor: cookieAction === 'loading' ? 'not-allowed' : 'pointer',
                  whiteSpace: 'nowrap' as const,
                }}
              >
                {cookieAction === 'loading' ? '⟳ …' : cookieAction === 'ok' ? '✓ Done' : '⟳ Auto-extract'}
              </button>
              <button
                onClick={() => setShowCookieHelp(h => !h)}
                title="How to export cookies from Chrome 127+"
                style={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  border: '1px solid #2A3558', background: showCookieHelp ? '#2A3558' : 'transparent',
                  color: '#4A5270', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >?</button>
            </div>

            {/* Row 2: path input + browse + import */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 12px 8px' }}>
              <input
                value={cookiePath}
                onChange={e => { setCookiePath(e.target.value); setCookieError(null) }}
                placeholder="Paste path to cookies.txt, hoặc bấm 📂"
                style={{
                  flex: 1, height: 28, padding: '0 8px', borderRadius: 6,
                  background: '#0D1019', border: `1px solid ${cookieError ? 'rgba(232,64,122,.4)' : '#2A3558'}`,
                  color: '#EEF0F8', fontSize: 10, fontFamily: 'monospace', outline: 'none',
                }}
              />
              <button
                onClick={handleBrowseCookies}
                title="Browse for cookies.txt file"
                style={{
                  height: 28, padding: '0 10px', borderRadius: 6, flexShrink: 0,
                  border: '1px solid #2A3558', background: '#0D1019',
                  color: '#8A93B0', fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap' as const,
                }}
              >📂</button>
              <button
                onClick={handleImportFile}
                disabled={!cookiePath.trim() || cookieAction === 'loading'}
                style={{
                  height: 28, padding: '0 12px', borderRadius: 6, flexShrink: 0,
                  border: '1px solid rgba(123,97,255,.35)', background: cookiePath.trim() ? 'rgba(123,97,255,.15)' : 'transparent',
                  color: cookiePath.trim() ? '#7B61FF' : '#2A3558', fontSize: 10, fontWeight: 700,
                  cursor: cookiePath.trim() && cookieAction !== 'loading' ? 'pointer' : 'not-allowed',
                  whiteSpace: 'nowrap' as const, transition: 'all .12s',
                }}
              >
                {cookieAction === 'loading' ? '⟳ Importing…' : 'Import'}
              </button>
            </div>

            {/* Error row */}
            {cookieError && (
              <div style={{ padding: '0 12px 8px' }}>
                <div style={{ padding: '6px 10px', borderRadius: 6, background: 'rgba(232,64,122,.08)', border: '1px solid rgba(232,64,122,.2)', fontSize: 10, color: '#E8407A' }}>
                  ⚠ {cookieError}
                </div>
              </div>
            )}

            {/* Collapsible instructions */}
            {showCookieHelp && (
              <div style={{ padding: '0 12px 10px', borderTop: '1px solid #1C2438' }}>
                <div style={{ paddingTop: 8, fontSize: 10, color: '#7B61FF', fontWeight: 700, marginBottom: 4 }}>
                  Chrome 127+ — export with extension:
                </div>
                <ol style={{ margin: 0, paddingLeft: 16, fontSize: 10, color: '#8A93B0', lineHeight: 1.9 }}>
                  <li>Cài <strong style={{ color: '#EEF0F8' }}>"Get cookies.txt LOCALLY"</strong> trên Chrome Web Store</li>
                  <li>Mở <strong style={{ color: '#EEF0F8' }}>youtube.com</strong> — đăng nhập trước</li>
                  <li>Click extension → <strong style={{ color: '#EEF0F8' }}>Export cookies for this tab</strong></li>
                  <li>Lưu file → paste path vào ô trên → bấm <strong style={{ color: '#EEF0F8' }}>Import</strong></li>
                </ol>
              </div>
            )}
          </div>
        )}

        {/* URL input */}
        <div style={{
          display: 'flex',
          background: '#0D1019',
          border: `1px solid ${error ? '#E8407A' : inputValid ? 'rgba(123,97,255,.4)' : '#1C2438'}`,
          borderRadius: 10,
          overflow: 'hidden',
          marginBottom: 10,
          transition: 'border-color .15s',
        }}>
          <input
            ref={inputRef}
            value={url}
            onChange={(e) => { setUrl(e.target.value); setError(null) }}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder="Paste YouTube, TikTok, Instagram, Facebook URL…"
            style={{
              flex: 1, height: 42, padding: '0 14px',
              background: 'transparent', border: 'none', outline: 'none',
              fontSize: 12, color: '#EEF0F8', fontFamily: 'monospace',
            }}
          />
          {!url && (
            <button
              onClick={handlePaste}
              title="Paste from clipboard"
              style={{
                height: 42, padding: '0 12px', background: 'transparent',
                border: 'none', borderLeft: '1px solid #1C2438',
                color: '#4A5270', fontSize: 11, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
                transition: 'color .12s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = '#8A93B0')}
              onMouseLeave={e => (e.currentTarget.style.color = '#4A5270')}
            >
              📋 Paste
            </button>
          )}
          {url && (
            <button
              onClick={() => { setUrl(''); setError(null) }}
              style={{
                height: 42, width: 36, background: 'transparent',
                border: 'none', borderLeft: '1px solid #1C2438',
                color: '#4A5270', fontSize: 16, cursor: 'pointer',
              }}
            >
              ×
            </button>
          )}
          <button
            onClick={handleAdd}
            disabled={adding || !inputValid}
            style={{
              height: 42, padding: '0 20px', flexShrink: 0,
              background: inputValid
                ? adding ? 'rgba(123,97,255,.4)' : 'linear-gradient(135deg,#7B61FF,#5B8AFF)'
                : '#161C2C',
              border: 'none', borderLeft: '1px solid rgba(255,255,255,.06)',
              color: inputValid ? '#fff' : '#4A5270',
              fontSize: 12, fontWeight: 700, cursor: inputValid && !adding ? 'pointer' : 'not-allowed',
              transition: 'all .12s',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            {adding ? (
              <span style={{ display: 'inline-block', animation: 'dl-spin .8s linear infinite' }}>⟳</span>
            ) : '↓'} {adding ? 'Adding…' : 'Add'}
          </button>
        </div>

        {/* Options row */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 10, color: '#4A5270', fontWeight: 600 }}>Quality</span>
            <select
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              style={{
                background: '#111622', border: '1px solid #1C2438',
                borderRadius: 6, padding: '5px 8px', fontSize: 11,
                color: '#EEF0F8', outline: 'none', cursor: 'pointer',
              }}
            >
              <option value="best">Best</option>
              <option value="1080">1080p</option>
              <option value="720">720p</option>
              <option value="480">480p</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 10, color: '#4A5270', fontWeight: 600, flexShrink: 0 }}>Save to</span>
            <div
              onClick={pickDir}
              style={{
                flex: 1, height: 30, padding: '0 10px', borderRadius: 6, cursor: 'pointer',
                background: '#111622', border: '1px solid #1C2438',
                fontSize: 10, color: outputDir ? '#8A93B0' : '#4A5270',
                display: 'flex', alignItems: 'center', overflow: 'hidden',
                fontFamily: 'monospace', whiteSpace: 'nowrap' as const,
                transition: 'border-color .12s',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#2A3558')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = '#1C2438')}
            >
              📁 {outputDir || 'Click to choose folder…'}
            </div>
          </div>
        </div>

        {error && (
          <div style={{
            marginTop: 10, padding: '8px 12px',
            background: 'rgba(232,64,122,.08)', border: '1px solid rgba(232,64,122,.2)',
            borderRadius: 8, fontSize: 11, color: '#E8407A', lineHeight: 1.5,
          }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {/* Queue */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
        {jobs.length === 0
          ? <EmptyQueue />
          : jobs.map((job) => <DownloadCard key={job.id} job={job} onCancel={cancelJob} />)
        }
      </div>
    </div>
  )
}
