import { useEffect, useRef, useState } from 'react'
import {
  startBatch, listJobs, cancelJob, subscribeJob,
  formatFilesize, platformLabel, platformColor,
  type DownloadJob,
} from '@/api/platformDownloader'

const QUALITY_OPTS = [
  { v: 'best',  l: 'Best'  },
  { v: '1080p', l: '1080p' },
  { v: '720p',  l: '720p'  },
  { v: '480p',  l: '480p'  },
]

// ── DownloadCard ───────────────────────────────────────────────────────────────

function DownloadCard({
  job, onCancel, onRetry,
}: { job: DownloadJob; onCancel: (id: string) => void; onRetry: (job: DownloadJob) => void }) {
  const isDone   = job.status === 'done'
  const isFailed = job.status === 'failed'
  const isQueued = job.status === 'queued'
  const isActive = job.status === 'downloading' || isQueued
  const color    = platformColor(job.platform)
  const label    = platformLabel(job.platform)

  const displayName = job.filename || job.title || ''
  const displayUrl  = job.url ? (job.url.length > 52 ? job.url.slice(0, 52) + '…' : job.url) : ''

  const openFolder = () => {
    const dir = job.output_dir || (job.output_path
      ? (() => { const sep = job.output_path.includes('\\') ? '\\' : '/'; return job.output_path.substring(0, job.output_path.lastIndexOf(sep)) })()
      : '')
    if (dir) window.electronAPI?.openPath?.(dir)
  }

  const copyPath = () => {
    if (job.output_path) navigator.clipboard.writeText(job.output_path).catch(() => {})
  }

  return (
    <div style={{
      background: 'var(--bg-card)', borderRadius: 8,
      border: '1px solid var(--border)',
      display: 'flex', overflow: 'hidden',
      transition: 'border-color .15s',
    }}>
      {/* Left accent */}
      <div style={{
        width: 3, flexShrink: 0,
        background: isDone ? 'var(--ok)' : isFailed ? 'var(--fail)' : isQueued ? 'var(--border-hi)' : color,
        opacity: isQueued ? 0.4 : 1,
      }} />

      <div style={{ flex: 1, minWidth: 0, padding: '10px 12px' }}>
        {/* Row 1: platform badge + name + cancel */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
          <span style={{
            fontSize: 8, fontWeight: 900, padding: '2px 5px', borderRadius: 4, flexShrink: 0, marginTop: 1,
            background: color + '18', border: `1px solid ${color}30`, color,
            fontFamily: 'var(--fh)', letterSpacing: '.02em',
          }}>
            {label.slice(0, 3).toUpperCase()}
          </span>

          <div style={{ flex: 1, minWidth: 0 }}>
            {displayName ? (
              <>
                <div style={{
                  fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.3,
                }}>
                  {displayName}
                </div>
                <div style={{
                  fontSize: 9, color: 'var(--text-3)', marginTop: 1,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {displayUrl}
                </div>
              </>
            ) : (
              <div style={{
                fontSize: 11, color: 'var(--text-2)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {displayUrl}
              </div>
            )}
          </div>

          {isActive && (
            <button onClick={() => onCancel(job.id)} style={{
              flexShrink: 0, padding: '2px 7px', borderRadius: 5,
              fontSize: 10, fontWeight: 700, cursor: 'pointer',
              border: '1px solid rgba(232,64,122,.3)', background: 'rgba(232,64,122,.08)',
              color: 'var(--fail)', lineHeight: 1,
            }}>✕</button>
          )}
        </div>

        {/* Active: progress */}
        {isActive && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ flex: 1, height: 4, borderRadius: 99, background: 'var(--bg-hover)', overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 99,
                  width: isQueued ? '100%' : `${Math.min(100, job.progress)}%`,
                  background: isQueued
                    ? 'repeating-linear-gradient(90deg,var(--border) 0,var(--border-hi) 8px,var(--border) 16px)'
                    : `linear-gradient(90deg, ${color}, ${color}bb)`,
                  transition: isQueued ? 'none' : 'width .4s ease',
                  boxShadow: isQueued ? 'none' : `0 0 6px ${color}55`,
                  animation: isQueued ? 'dl-stripe 1s linear infinite' : 'none',
                }} />
              </div>
              <span style={{ fontSize: 10, fontWeight: 700, color: isQueued ? 'var(--text-3)' : 'var(--text-2)', flexShrink: 0 }}>
                {isQueued ? 'queued' : `${job.progress}%`}
              </span>
            </div>
            {!isQueued && (job.speed_str || job.eta_str) && (
              <div style={{ display: 'flex', gap: 8, fontSize: 9, color: 'var(--text-3)' }}>
                {job.speed_str && <span style={{ color }}>{job.speed_str}</span>}
                {job.eta_str && <span>ETA {job.eta_str}</span>}
              </div>
            )}
          </div>
        )}

        {/* Done */}
        {isDone && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--ok)' }}>✓ Done</span>
            {job.height > 0 && (
              <span style={{
                fontSize: 9, padding: '1px 5px', borderRadius: 4, fontWeight: 600,
                background: 'rgba(0,200,150,.1)', color: 'var(--ok)', border: '1px solid rgba(0,200,150,.2)',
              }}>
                {job.height}p{job.fps > 30 ? ` · ${Math.round(job.fps)}fps` : ''}
              </span>
            )}
            {job.filesize > 0 && (
              <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{formatFilesize(job.filesize)}</span>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
              {job.output_path && (
                <button onClick={copyPath} title="Copy path" style={{
                  fontSize: 9, padding: '2px 7px', borderRadius: 5, cursor: 'pointer',
                  border: '1px solid var(--border)', background: 'var(--bg-hover)', color: 'var(--text-3)',
                }}>Copy</button>
              )}
              {job.output_dir && (
                <button onClick={openFolder} title="Open folder" style={{
                  fontSize: 9, padding: '2px 7px', borderRadius: 5, cursor: 'pointer',
                  border: '1px solid var(--border)', background: 'var(--bg-hover)', color: 'var(--text-3)',
                }}>📂</button>
              )}
            </div>
          </div>
        )}

        {/* Failed */}
        {isFailed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--fail)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              ✕ {job.error_msg || 'Download failed'}
            </span>
            <button onClick={() => onRetry(job)} style={{
              flexShrink: 0, padding: '2px 9px', borderRadius: 5,
              fontSize: 10, fontWeight: 700, cursor: 'pointer',
              border: '1px solid var(--border)', background: 'var(--bg-hover)', color: 'var(--text-2)',
            }}>↺ Retry</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────

export function DownloaderScreen() {
  const [urlInput, setUrlInput]     = useState('')
  const [outputDir, setOutputDir]   = useState('')
  const [quality, setQuality]       = useState('best')
  const [jobs, setJobs]             = useState<DownloadJob[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const wsRefs = useRef<Map<string, WebSocket>>(new Map())

  useEffect(() => {
    listJobs().then(jobsList => {
      setJobs(jobsList)
      for (const j of jobsList) {
        if (j.status === 'queued' || j.status === 'downloading') subscribeNewJob(j.id)
      }
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function updateJob(updated: DownloadJob) {
    setJobs(prev => {
      const idx = prev.findIndex(j => j.id === updated.id)
      if (idx === -1) return [updated, ...prev]
      const next = [...prev]; next[idx] = updated; return next
    })
  }

  function subscribeNewJob(jobId: string) {
    if (wsRefs.current.has(jobId)) return
    const ws = subscribeJob(jobId, updateJob, () => wsRefs.current.delete(jobId))
    wsRefs.current.set(jobId, ws)
  }

  async function handleDownload() {
    const urls = urlInput.split('\n').map(u => u.trim()).filter(Boolean)
    if (!urls.length) return
    if (!outputDir.trim()) { setError('Vui lòng chọn thư mục lưu'); return }
    setSubmitting(true); setError(null)
    try {
      const res = await startBatch(urls, outputDir, quality)
      for (const j of res.jobs) {
        setJobs(prev => [{
          id: j.job_id, url: j.url, platform: j.platform,
          status: 'queued', progress: 0, speed_str: '', eta_str: '',
          output_path: '', output_dir: outputDir, filename: '', title: '',
          duration: 0, height: 0, fps: 0, filesize: 0, error_msg: '',
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }, ...prev])
        subscribeNewJob(j.job_id)
      }
      setUrlInput('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Tải thất bại')
    } finally { setSubmitting(false) }
  }

  async function handleCancel(jobId: string) {
    wsRefs.current.get(jobId)?.close()
    wsRefs.current.delete(jobId)
    await cancelJob(jobId).catch(() => {})
    setJobs(prev => prev.filter(j => j.id !== jobId))
  }

  async function handleRetry(job: DownloadJob) {
    setError(null)
    try {
      const res = await startBatch([job.url], job.output_dir || outputDir, quality)
      for (const j of res.jobs) {
        setJobs(prev => [{
          id: j.job_id, url: j.url, platform: j.platform,
          status: 'queued', progress: 0, speed_str: '', eta_str: '',
          output_path: '', output_dir: job.output_dir || outputDir,
          filename: '', title: job.title, duration: 0,
          height: 0, fps: 0, filesize: 0, error_msg: '',
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }, ...prev.filter(p => p.id !== job.id)])
        subscribeNewJob(j.job_id)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Retry thất bại')
    }
  }

  function handleClearDone() {
    setJobs(prev => prev.filter(j => j.status === 'queued' || j.status === 'downloading'))
  }

  const activeCount = jobs.filter(j => j.status === 'downloading' || j.status === 'queued').length
  const doneCount   = jobs.filter(j => j.status === 'done').length
  const failedCount = jobs.filter(j => j.status === 'failed').length
  const urlCount    = urlInput.split('\n').map(u => u.trim()).filter(Boolean).length
  const canSubmit   = !submitting && urlInput.trim().length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-base)', overflow: 'hidden' }}>
      <style>{`
        @keyframes dl-pulse  { 0%,100%{opacity:1}  50%{opacity:.4} }
        @keyframes dl-stripe { 0%{background-position:0 0} 100%{background-position:32px 0} }
      `}</style>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        padding: '12px 16px 10px', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontFamily: 'var(--fh)', fontSize: 13, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.6px' }}>
            DOWNLOADER
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 1 }}>
            YouTube · TikTok · Instagram · Facebook · và hơn thế
          </div>
        </div>

        {(activeCount > 0 || doneCount > 0 || failedCount > 0) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            {activeCount > 0 && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(123,97,255,.3)',
              }}>
                {activeCount} đang tải
              </span>
            )}
            {doneCount > 0 && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                background: 'rgba(0,200,150,.1)', color: 'var(--ok)', border: '1px solid rgba(0,200,150,.2)',
              }}>
                {doneCount} xong
              </span>
            )}
            {failedCount > 0 && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                background: 'rgba(232,64,122,.1)', color: 'var(--fail)', border: '1px solid rgba(232,64,122,.25)',
              }}>
                {failedCount} lỗi
              </span>
            )}
            {(doneCount > 0 || failedCount > 0) && (
              <button onClick={handleClearDone} style={{
                fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-3)', cursor: 'pointer',
              }}>
                Xóa xong
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Input panel ────────────────────────────────────────────────────── */}
      <div style={{ padding: '10px 16px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg-panel)' }}>

        {/* URL input */}
        <div style={{ position: 'relative', marginBottom: 8 }}>
          <textarea
            value={urlInput}
            onChange={e => setUrlInput(e.target.value)}
            placeholder={'Dán URL vào đây — mỗi URL một dòng\nhttps://youtube.com/watch?v=...\nhttps://tiktok.com/@user/video/...'}
            rows={3}
            style={{
              width: '100%', padding: '8px 10px', borderRadius: 7, fontSize: 11,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-1)', resize: 'none', outline: 'none',
              fontFamily: 'var(--fb)', boxSizing: 'border-box', lineHeight: 1.65,
              transition: 'border-color .15s',
            }}
            onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
            onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
          />
          {urlCount > 0 && (
            <span style={{
              position: 'absolute', bottom: 7, right: 8,
              fontSize: 9, fontWeight: 700, color: 'var(--accent)',
              background: 'var(--bg-card)', padding: '0 3px',
            }}>
              {urlCount} URL
            </span>
          )}
        </div>

        {/* Folder input */}
        <input
          value={outputDir}
          onChange={e => setOutputDir(e.target.value)}
          placeholder="Thư mục lưu — D:\Videos\Downloads"
          style={{
            width: '100%', padding: '6px 10px', borderRadius: 7, fontSize: 11,
            border: '1px solid var(--border)', background: 'var(--bg-card)',
            color: 'var(--text-1)', outline: 'none', boxSizing: 'border-box',
            fontFamily: 'var(--fb)', transition: 'border-color .15s', marginBottom: 8,
          }}
          onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
          onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
        />

        {/* Quality + button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ display: 'flex', gap: 3, background: 'var(--bg-hover)', borderRadius: 6, padding: 2 }}>
            {QUALITY_OPTS.map(({ v, l }) => (
              <button key={v} onClick={() => setQuality(v)} style={{
                padding: '3px 10px', borderRadius: 5, fontSize: 10, fontWeight: 700, cursor: 'pointer',
                border: 'none', transition: 'all .12s',
                background: quality === v ? 'var(--bg-card)' : 'transparent',
                color: quality === v ? 'var(--accent)' : 'var(--text-3)',
                boxShadow: quality === v ? '0 1px 4px rgba(0,0,0,.18)' : 'none',
              }}>{l}</button>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <button
            onClick={handleDownload}
            disabled={!canSubmit}
            style={{
              padding: '7px 20px', borderRadius: 7, border: 'none',
              fontSize: 12, fontWeight: 700, fontFamily: 'var(--fh)', letterSpacing: '.4px',
              cursor: canSubmit ? 'pointer' : 'not-allowed', transition: 'all .15s',
              background: canSubmit ? 'var(--grad-btn)' : 'var(--bg-hover)',
              color: canSubmit ? '#fff' : 'var(--text-3)',
              boxShadow: canSubmit ? '0 3px 12px rgba(123,97,255,.3)' : 'none',
            }}
          >
            {submitting ? '…' : '↓ TẢI XUỐNG'}
          </button>
        </div>

        {error && (
          <div style={{
            marginTop: 8, fontSize: 11, color: 'var(--fail)',
            padding: '6px 10px', borderRadius: 6,
            background: 'rgba(232,64,122,.07)', border: '1px solid rgba(232,64,122,.2)',
          }}>
            {error}
          </div>
        )}
      </div>

      {/* ── Queue ──────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {jobs.length === 0 ? (
          <div style={{
            height: '100%', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 8, opacity: .35,
          }}>
            <div style={{ fontSize: 32 }}>↓</div>
            <div style={{ fontFamily: 'var(--fh)', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', letterSpacing: '.6px' }}>
              CHƯA CÓ VIDEO
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-3)' }}>Dán URL vào ô trên và nhấn Tải xuống</div>
          </div>
        ) : (
          <>
            {/* Queue count header */}
            <div style={{
              padding: '8px 16px 4px', fontSize: 9, fontWeight: 700,
              color: 'var(--text-3)', letterSpacing: '.08em', textTransform: 'uppercase',
            }}>
              Hàng đợi — {jobs.length} video
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '0 16px 16px' }}>
              {jobs.map(job => (
                <DownloadCard key={job.id} job={job} onCancel={handleCancel} onRetry={handleRetry} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
