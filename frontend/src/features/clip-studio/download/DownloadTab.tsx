import { useState, useEffect, useRef, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import {
  listJobs, startDownload, cancelJob,
  platformLabel, platformColor, formatFilesize,
} from '../../../api/platformDownloader'
import type { DownloadJob } from '../../../api/platformDownloader'

const POLL_MS = 1500

const STATUS_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  queued:      { color: '#6b7280', bg: 'rgba(107,114,128,.12)', label: 'Queued' },
  downloading: { color: '#a855f7', bg: 'rgba(168,85,247,.12)',  label: 'Downloading' },
  done:        { color: '#34C878', bg: 'rgba(52,200,120,.12)',  label: 'Done' },
  failed:      { color: '#ef4444', bg: 'rgba(239,68,68,.12)',   label: 'Failed' },
}

function JobCard({ job, onCancel }: { job: DownloadJob; onCancel: (id: string) => void }) {
  const st = STATUS_STYLE[job.status] ?? STATUS_STYLE.queued
  const pColor = platformColor(job.platform)
  const isActive = job.status === 'downloading'
  const isDone = job.status === 'done'
  const isFailed = job.status === 'failed'

  return (
    <div style={{
      display: 'flex',
      borderRadius: 10,
      overflow: 'hidden',
      background: 'var(--bg-card)',
      border: `1px solid ${isActive ? 'rgba(168,85,247,.25)' : 'var(--border)'}`,
      boxShadow: isActive ? '0 0 12px rgba(168,85,247,.08)' : 'none',
      transition: 'border-color .15s',
    }}>
      {/* Top accent bar */}
      <div style={{ width: 3, flexShrink: 0, background: `linear-gradient(180deg,${pColor},${pColor}55)` }} />

      <div style={{ flex: 1, padding: '10px 12px', minWidth: 0 }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          {/* Platform badge */}
          <span style={{
            fontSize: 9, fontWeight: 800, padding: '2px 6px', borderRadius: 4, flexShrink: 0,
            background: `${pColor}22`, color: pColor, border: `1px solid ${pColor}44`,
            letterSpacing: '.04em',
          }}>
            {platformLabel(job.platform)}
          </span>

          {/* Title */}
          <span style={{
            flex: 1, fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {job.title || job.url}
          </span>

          {/* Status badge */}
          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20, flexShrink: 0,
            background: st.bg, color: st.color,
            animation: isActive ? 'dl-pulse 1.4s ease-in-out infinite' : 'none',
          }}>
            {st.label}
          </span>
        </div>

        {/* Progress bar */}
        {(isActive || isDone) && (
          <div style={{ height: 3, borderRadius: 99, background: 'rgba(255,255,255,.07)', overflow: 'hidden', marginBottom: 6 }}>
            <div style={{
              height: '100%', borderRadius: 99,
              width: isDone ? '100%' : `${job.progress}%`,
              background: isDone
                ? 'linear-gradient(90deg,#34C878,#22c55e)'
                : `linear-gradient(90deg,${pColor},#a855f7)`,
              transition: 'width .4s ease',
              boxShadow: isActive ? `0 0 6px ${pColor}80` : 'none',
            }} />
          </div>
        )}

        {/* Meta row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
          {isActive && (
            <>
              <span style={{ fontSize: 10, color: st.color, fontWeight: 700, fontFamily: 'monospace' }}>
                {job.progress}%
              </span>
              {job.speed_str && (
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{job.speed_str}</span>
              )}
              {job.eta_str && (
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{job.eta_str}</span>
              )}
            </>
          )}
          {isDone && job.filename && (
            <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
              {job.filename}
            </span>
          )}
          {isDone && job.filesize > 0 && (
            <span style={{ fontSize: 10, color: '#34C878' }}>{formatFilesize(job.filesize)}</span>
          )}
          {isFailed && (
            <span style={{ fontSize: 10, color: '#ef4444' }}>{job.error_msg || 'Download failed'}</span>
          )}
          <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 'auto' }}>
            {new Date(job.created_at).toLocaleTimeString()}
          </span>

          {/* Cancel button */}
          {(job.status === 'queued' || job.status === 'downloading') && (
            <button
              onClick={() => onCancel(job.id)}
              style={{
                height: 20, padding: '0 8px', borderRadius: 5, flexShrink: 0,
                border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--text-3)', fontSize: 10, fontWeight: 600, cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function DownloadTab({ lang: _lang }: { lang: Lang }) {
  const [url, setUrl]         = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [quality, setQuality] = useState('best')
  const [jobs, setJobs]       = useState<DownloadJob[]>([])
  const [adding, setAdding]   = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const pollRef               = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await listJobs(50)
      setJobs(list)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    refresh()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [refresh])

  const pickDir = async () => {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setOutputDir(dir)
  }

  const handleAdd = async () => {
    const v = url.trim()
    if (!v) return
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

  const handleCancel = async (id: string) => {
    try { await cancelJob(id); await refresh() } catch { /* ignore */ }
  }

  const activeCount = jobs.filter((j) => j.status === 'downloading').length
  const doneCount   = jobs.filter((j) => j.status === 'done').length
  const failedCount = jobs.filter((j) => j.status === 'failed').length

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-base)' }}>
      <style>{`@keyframes dl-pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>

      {/* ── Header ── */}
      <div style={{
        padding: '14px 20px 12px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        background: 'linear-gradient(180deg,rgba(77,124,255,.04) 0%,transparent 100%)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>⬇ Downloader</span>
          <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
            {activeCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'rgba(168,85,247,.12)', color: '#a855f7', border: '1px solid rgba(168,85,247,.2)' }}>
                {activeCount} active
              </span>
            )}
            {doneCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(52,200,120,.1)', color: '#34C878' }}>
                {doneCount} done
              </span>
            )}
            {failedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(239,68,68,.1)', color: '#ef4444' }}>
                {failedCount} failed
              </span>
            )}
          </div>
        </div>

        {/* URL row */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input
            value={url}
            onChange={(e) => { setUrl(e.target.value); setError(null) }}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder="https://youtube.com/watch?v=... or TikTok / Instagram URL"
            style={{
              flex: 1, height: 38, padding: '0 12px',
              background: 'var(--bg-card)', border: `1px solid ${error ? '#ef4444' : 'var(--border)'}`,
              borderRadius: 8, fontSize: 12, color: 'var(--text-1)', outline: 'none',
              fontFamily: 'monospace',
            }}
          />
          <button
            onClick={handleAdd}
            disabled={adding || !url.trim()}
            style={{
              height: 38, padding: '0 18px', borderRadius: 8, flexShrink: 0,
              background: url.trim() ? 'linear-gradient(135deg,#a855f7,#4d7cff)' : 'var(--bg-card)',
              border: 'none', color: url.trim() ? '#fff' : 'var(--text-3)',
              fontSize: 12, fontWeight: 700, cursor: url.trim() ? 'pointer' : 'not-allowed',
              opacity: adding ? .6 : 1,
            }}
          >
            {adding ? '…' : 'ADD'}
          </button>
        </div>

        {/* Options row */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>Quality</span>
          <select
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '4px 8px', fontSize: 11,
              color: 'var(--text-1)', outline: 'none', cursor: 'pointer',
            }}
          >
            <option value="best">Best Available</option>
            <option value="1080">1080p</option>
            <option value="720">720p</option>
            <option value="480">480p</option>
          </select>

          <span style={{ fontSize: 11, color: 'var(--text-3)', flexShrink: 0, marginLeft: 4 }}>Save to</span>
          <div
            onClick={pickDir}
            style={{
              flex: 1, height: 28, padding: '0 10px', borderRadius: 6, cursor: 'pointer',
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              fontSize: 11, color: outputDir ? 'var(--text-2)' : 'var(--text-3)',
              display: 'flex', alignItems: 'center', overflow: 'hidden', whiteSpace: 'nowrap' as const,
              fontFamily: 'monospace',
            }}
          >
            {outputDir || 'Click to choose folder…'}
          </div>
        </div>

        {error && <div style={{ fontSize: 11, color: '#ef4444', marginTop: 6 }}>⚠ {error}</div>}
      </div>

      {/* ── Job list ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {jobs.length === 0 ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 12, color: 'var(--text-3)',
          }}>
            <span style={{ fontSize: 36, opacity: .2 }}>⬇</span>
            <span style={{ fontSize: 13 }}>Paste a URL above to start downloading</span>
            <span style={{ fontSize: 11, opacity: .6 }}>YouTube · TikTok · Instagram · Facebook</span>
          </div>
        ) : (
          jobs.map((job) => <JobCard key={job.id} job={job} onCancel={handleCancel} />)
        )}
      </div>
    </div>
  )
}
