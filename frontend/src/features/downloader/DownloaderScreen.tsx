import { useEffect, useRef, useState } from 'react'
import {
  startBatch, listJobs, cancelJob, subscribeJob,
  formatFilesize, platformLabel, platformColor,
  type DownloadJob,
} from '../../api/platformDownloader'

// ── Platform chips ─────────────────────────────────────────────────────────────

const PLATFORMS = [
  { id: 'youtube',   label: 'YouTube',   color: '#FF4040' },
  { id: 'tiktok',    label: 'TikTok',    color: '#00E5C8' },
  { id: 'instagram', label: 'Instagram', color: '#C13584' },
  { id: 'facebook',  label: 'Facebook',  color: '#4D7CFF' },
  { id: 'twitter',   label: 'X / Twitter', color: '#8A93B0' },
  { id: 'bilibili',  label: 'Bilibili',  color: '#00A1D6' },
]

const QUALITY_OPTS = [
  { v: 'best',  l: 'Best'  },
  { v: '1080p', l: '1080p' },
  { v: '720p',  l: '720p'  },
  { v: '480p',  l: '480p'  },
]

// ── Sub-components ─────────────────────────────────────────────────────────────

function ProgressBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 3, borderRadius: 99, background: 'var(--bg-hover)', overflow: 'hidden', width: '100%' }}>
      <div style={{
        height: '100%', width: `${Math.min(100, value)}%`, borderRadius: 99,
        background: `linear-gradient(90deg, ${color}, ${color}99)`,
        transition: 'width .4s ease',
        boxShadow: `0 0 8px ${color}55`,
      }} />
    </div>
  )
}

function DownloadCard({ job, onCancel }: { job: DownloadJob; onCancel: (id: string) => void }) {
  const isDone   = job.status === 'done'
  const isFailed = job.status === 'failed'
  const isActive = job.status === 'downloading' || job.status === 'queued'
  const color    = platformColor(job.platform)
  const label    = platformLabel(job.platform)

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
      transition: 'border-color .15s',
    }}>
      {/* Top color accent */}
      <div style={{ height: 2, background: `linear-gradient(90deg, ${color}, transparent)` }} />

      <div style={{ padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        {/* Platform badge */}
        <div style={{
          width: 32, height: 32, borderRadius: 6, flexShrink: 0,
          background: color + '18', border: `1px solid ${color}33`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 9, fontWeight: 900, color: color, letterSpacing: '-.02em',
          fontFamily: 'var(--fh)',
        }}>
          {label.slice(0, 3).toUpperCase()}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Title */}
          <div style={{
            fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            marginBottom: 4,
          }}>
            {job.filename || job.title || job.url}
          </div>

          {isActive && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <ProgressBar value={job.progress} color={color} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10 }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', background: color,
                  flexShrink: 0, boxShadow: `0 0 5px ${color}`,
                  animation: 'dl-pulse 1.4s ease-in-out infinite',
                }} />
                <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>
                  {job.status === 'queued' ? 'Queued…' : `${job.progress}%`}
                </span>
                {job.speed_str && <span style={{ color }}>{job.speed_str}</span>}
                {job.eta_str && <span style={{ color: 'var(--text-3)' }}>· {job.eta_str}</span>}
              </div>
            </div>
          )}

          {isDone && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, color: 'var(--ok)', fontWeight: 700 }}>✓ Done</span>
              {job.height > 0 && (
                <span style={{
                  fontSize: 9, padding: '1px 5px', borderRadius: 4,
                  background: 'rgba(0,200,150,.12)', color: 'var(--ok)',
                  border: '1px solid rgba(0,200,150,.2)', fontWeight: 600,
                }}>
                  {job.height}p{job.fps > 30 ? `·${Math.round(job.fps)}fps` : ''}
                </span>
              )}
              {job.filesize > 0 && (
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{formatFilesize(job.filesize)}</span>
              )}
            </div>
          )}

          {isFailed && (
            <div style={{ fontSize: 10, color: 'var(--fail)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <span>✕</span>
              <span>{job.error_msg || 'Download failed'}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ flexShrink: 0, alignSelf: 'center' }}>
          {isActive && (
            <button onClick={() => onCancel(job.id)} style={{
              padding: '3px 9px', borderRadius: 5, fontSize: 10, fontWeight: 700, cursor: 'pointer',
              border: '1px solid var(--border-hi)', background: 'rgba(232,64,122,.1)',
              color: 'var(--fail)', transition: 'all .12s',
            }}>
              ✕
            </button>
          )}
          {isDone && job.output_path && (
            <button
              onClick={() => { const w = window as any; w.electronAPI?.openPath?.(job.output_dir) }}
              style={{
                padding: '3px 9px', borderRadius: 5, fontSize: 10, fontWeight: 700, cursor: 'pointer',
                border: '1px solid var(--border-hi)', background: 'var(--accent-dim)',
                color: 'var(--accent)', transition: 'all .12s',
              }}
            >
              ↗
            </button>
          )}
        </div>
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

  useEffect(() => { listJobs().then(setJobs).catch(() => {}) }, [])

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
    } catch (e: any) {
      setError(e.message || 'Tải thất bại')
    } finally { setSubmitting(false) }
  }

  async function handleCancel(jobId: string) {
    wsRefs.current.get(jobId)?.close()
    wsRefs.current.delete(jobId)
    await cancelJob(jobId).catch(() => {})
    setJobs(prev => prev.filter(j => j.id !== jobId))
  }

  const activeCount = jobs.filter(j => j.status === 'downloading' || j.status === 'queued').length
  const doneCount   = jobs.filter(j => j.status === 'done').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-base)' }}>
      <style>{`@keyframes dl-pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div style={{
        padding: '14px 18px 12px', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div>
            <div style={{ fontFamily: 'var(--fh)', fontSize: 15, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.5px' }}>
              DOWNLOADER
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>
              No watermark · Best quality · YouTube · TikTok · IG · và hơn thế
            </div>
          </div>
          {(activeCount > 0 || doneCount > 0) && (
            <div style={{ display: 'flex', gap: 6 }}>
              {activeCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                  background: 'var(--accent-dim)', color: 'var(--accent)',
                  border: '1px solid rgba(123,97,255,.3)',
                }}>
                  {activeCount} đang tải
                </span>
              )}
              {doneCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                  background: 'rgba(0,200,150,.12)', color: 'var(--ok)',
                  border: '1px solid rgba(0,200,150,.2)',
                }}>
                  {doneCount} xong
                </span>
              )}
            </div>
          )}
        </div>

        {/* Platform badges */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {PLATFORMS.map(p => (
            <span key={p.id} style={{
              fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
              background: p.color + '15', border: `1px solid ${p.color}25`, color: p.color,
              fontFamily: 'var(--fh)', letterSpacing: '.4px',
            }}>
              {p.label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Input panel ──────────────────────────────────────────────────── */}
      <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg-panel)' }}>

        {/* URL textarea */}
        <div className="cfg-sec-hd" style={{ marginBottom: 6 }}>
          <span>URL VIDEO</span>
          <span className="cfg-sec-api">1 URL mỗi dòng</span>
        </div>
        <textarea
          value={urlInput}
          onChange={e => setUrlInput(e.target.value)}
          placeholder={'https://youtube.com/watch?v=...\nhttps://tiktok.com/@user/video/...'}
          rows={3}
          style={{
            width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 11,
            border: '1px solid var(--border)', background: 'var(--bg-card)',
            color: 'var(--text-1)', resize: 'vertical', outline: 'none',
            fontFamily: 'var(--fb)', boxSizing: 'border-box', lineHeight: 1.6,
            transition: 'border-color .15s',
          }}
          onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
          onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
        />

        {/* Folder row */}
        <div style={{ marginTop: 8 }}>
          <div className="cfg-sec-hd" style={{ marginBottom: 5 }}>
            <span>THƯ MỤC LƯU</span>
          </div>
          <input
            value={outputDir}
            onChange={e => setOutputDir(e.target.value)}
            placeholder="D:\Videos\Downloads"
            style={{
              width: '100%', padding: '6px 10px', borderRadius: 6, fontSize: 11,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-1)', outline: 'none', boxSizing: 'border-box',
              fontFamily: 'var(--fb)', transition: 'border-color .15s',
            }}
            onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
            onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
          />
        </div>

        {/* Quality + button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {QUALITY_OPTS.map(({ v, l }) => (
              <div key={v}
                className={`seg-b${quality === v ? ' on' : ''}`}
                onClick={() => setQuality(v)}
                style={{ fontSize: 10 }}>
                {l}
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <button
            onClick={handleDownload}
            disabled={submitting || !urlInput.trim()}
            style={{
              padding: '7px 22px', borderRadius: 6, border: 'none',
              fontSize: 12, fontWeight: 700, cursor: submitting || !urlInput.trim() ? 'not-allowed' : 'pointer',
              background: submitting || !urlInput.trim()
                ? 'var(--bg-card)'
                : 'var(--grad-btn)',
              color: submitting || !urlInput.trim() ? 'var(--text-3)' : '#fff',
              fontFamily: 'var(--fh)', letterSpacing: '.5px',
              boxShadow: submitting || !urlInput.trim() ? 'none' : '0 4px 14px rgba(123,97,255,.3)',
              transition: 'all .15s', whiteSpace: 'nowrap',
            }}
          >
            {submitting ? '…' : '↓ TẢI XUỐNG'}
          </button>
        </div>

        {error && (
          <div style={{
            marginTop: 8, fontSize: 11, color: 'var(--fail)',
            padding: '6px 10px', borderRadius: 6,
            background: 'rgba(232,64,122,.08)', border: '1px solid rgba(232,64,122,.2)',
          }}>
            {error}
          </div>
        )}
      </div>

      {/* ── Queue ────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {jobs.length === 0 ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 8, opacity: .4, padding: '48px 0',
          }}>
            <div style={{ fontSize: 28, color: 'var(--text-3)' }}>↓</div>
            <div style={{ fontFamily: 'var(--fh)', fontSize: 12, fontWeight: 700, color: 'var(--text-2)', letterSpacing: '.5px' }}>
              CHƯA CÓ VIDEO
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', textAlign: 'center' }}>
              Dán URL vào ô trên và nhấn Tải xuống
            </div>
          </div>
        ) : (
          jobs.map(job => <DownloadCard key={job.id} job={job} onCancel={handleCancel} />)
        )}
      </div>
    </div>
  )
}
