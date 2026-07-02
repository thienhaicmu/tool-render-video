import { useEffect, useState } from 'react'
import { AiSummaryCard } from './AiSummaryCard'
import { formatDateTime } from './jobs.utils'
import { getJob, getJobParts } from '@/api/jobs'
import { retryRender, resumeRender } from '@/api/render'
import { deleteJob } from '@/api/jobs'
import { useEditorStore } from '@/stores/editorStore'
import { useUIStore } from '@/stores/uiStore'
import { ApiError } from '@/api/client'
import { confirmDialog } from '@/components/ui/ConfirmDialog'
import { IconFolder, IconX } from '@/components/icons'
import { ClipPlayerModal } from '@/features/clip-studio/render/steps/ClipPlayerModal'
import { useT } from '@/features/clip-studio/render/i18n'
import { useI18n } from '@/i18n/useI18n'
import { submitClipFeedback, deleteClipFeedback } from '@/api/feedback'
import type { JobStatus, JobPart } from '@/types/api'

export interface JobDetailDrawerProps {
  jobId: string
  onClose: () => void
}

const STATUS_CFG: Record<string, { color: string; label: string }> = {
  completed:             { color: 'var(--ok)',     label: 'Xong'        },
  partial:               { color: 'var(--warn)',   label: 'Một phần'    },
  completed_with_errors: { color: 'var(--warn)',   label: 'Một phần'    },
  running:               { color: 'var(--accent)', label: 'Đang render' },
  queued:                { color: 'var(--accent)', label: 'Xếp hàng'   },
  failed:                { color: 'var(--fail)',   label: 'Lỗi'         },
  interrupted:           { color: 'var(--warn)',   label: 'Gián đoạn'   },
  cancelled:             { color: 'var(--text-3)', label: 'Đã hủy'      },
  canceled:              { color: 'var(--text-3)', label: 'Đã hủy'      },
  cancelling:            { color: 'var(--warn)',   label: 'Đang hủy'    },
}
const FALLBACK_ST = { color: 'var(--text-3)', label: '—' }
const TERMINAL = new Set(['completed', 'completed_with_errors', 'partial', 'failed', 'interrupted', 'cancelled', 'canceled'])

function parseMeta(payloadJson: string): { platform?: string; ratio?: string; source?: string } {
  try {
    const p = JSON.parse(payloadJson)
    return {
      platform: p.target_platform,
      ratio: p.aspect_ratio,
      source: p.youtube_url || p.source_video_path || p.url || p.path,
    }
  } catch { return {} }
}

function parseBestPartNo(resultJson: string): number | undefined {
  try {
    const r = JSON.parse(resultJson)
    return typeof r.best_part_no === 'number' ? r.best_part_no : undefined
  } catch { return undefined }
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <span style={{ fontSize: 8, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '.06em', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontSize: 10, color: 'var(--text-2)', fontWeight: 500 }}>{value}</span>
    </div>
  )
}

function ClipCard({ part, isBest, onPlay }: { part: JobPart; isBest: boolean; jobId: string; onPlay?: () => void }) {
  const isDone   = part.status === 'done'
  const isFailed = part.status === 'failed'
  const score    = part.viral_score > 0 ? part.viral_score : part.hook_score

  const openFolder = () => {
    if (!part.output_file) return
    const sep = part.output_file.includes('\\') ? '\\' : '/'
    const dir = part.output_file.substring(0, part.output_file.lastIndexOf(sep)) || part.output_file
    window.electronAPI?.openPath?.(dir)
  }

  return (
    <div
      onClick={part.status === 'done' && onPlay ? onPlay : undefined}
      style={{
      borderRadius: 8, overflow: 'hidden',
      border: `1px solid ${isBest ? 'rgba(123,97,255,.4)' : 'var(--border)'}`,
      background: 'var(--bg-card)',
      boxShadow: isBest ? '0 0 12px rgba(123,97,255,.15)' : 'none',
      cursor: part.status === 'done' && onPlay ? 'pointer' : 'default',
    }}>
      {/* Thumbnail placeholder — 9:16 aspect */}
      <div style={{
        aspectRatio: '9/16', width: '100%',
        background: isDone
          ? 'linear-gradient(160deg, rgba(123,97,255,.12), rgba(0,200,150,.08))'
          : isFailed
            ? 'rgba(232,64,122,.08)'
            : 'var(--bg-hover)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
        fontSize: 22, color: isFailed ? 'var(--fail)' : 'var(--text-3)', opacity: .5,
      }}>
        {isFailed ? '✕' : isDone ? '▶' : '…'}

        {/* Best badge */}
        {isBest && (
          <div style={{
            position: 'absolute', top: 5, left: 5,
            fontSize: 8, fontWeight: 900, padding: '2px 5px', borderRadius: 4,
            background: 'var(--accent)', color: '#fff',
            fontFamily: 'var(--fh)', letterSpacing: '.04em',
          }}>BEST</div>
        )}

        {/* Clip number */}
        <div style={{
          position: 'absolute', bottom: 5, right: 5,
          fontSize: 9, fontWeight: 700, color: 'var(--text-2)',
          background: 'rgba(0,0,0,.45)', padding: '1px 5px', borderRadius: 4,
        }}>#{part.part_no}</div>
      </div>

      {/* Info row */}
      <div style={{ padding: '5px 7px' }}>
        {isDone && score > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 3 }}>
            <div style={{ flex: 1, height: 2, borderRadius: 99, background: 'var(--bg-hover)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 99,
                width: `${Math.min(100, score)}%`,
                background: 'linear-gradient(90deg, var(--accent), var(--ok))',
              }} />
            </div>
            <span style={{ fontSize: 8, fontWeight: 700, color: 'var(--text-2)', flexShrink: 0 }}>
              {Math.round(score)}%
            </span>
          </div>
        )}
        {isFailed && (
          <div style={{ fontSize: 8, color: 'var(--fail)', lineHeight: 1.3 }}>
            {part.message ? part.message.slice(0, 40) : 'Failed'}
          </div>
        )}
        {isDone && part.output_file && (
          <button
            onClick={openFolder}
            style={{
              width: '100%', fontSize: 9, padding: '2px 0', borderRadius: 4,
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--text-3)', cursor: 'pointer',
            }}
          ><IconFolder size={13} /></button>
        )}
      </div>
    </div>
  )
}

export function JobDetailDrawer({ jobId, onClose }: JobDetailDrawerProps) {
  const [job, setJob]     = useState<JobStatus | null>(null)
  const [parts, setParts] = useState<JobPart[]>([])
  // P4.E — in-app player over the drawer's clip gallery.
  const [playerIdx, setPlayerIdx] = useState<number | null>(null)
  const [fbRatings, setFbRatings] = useState<Record<number, 1 | -1 | null>>({})
  const { lang } = useI18n()
  const tRender = useT(lang === 'vi' ? 'VI' : 'EN')
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const openEditor    = useEditorStore(s => s.openEditor)
  const setActivePanel = useUIStore(s => s.setActivePanel)
  const addNotification = useUIStore(s => s.addNotification)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setParts([])
    getJob(jobId)
      .then(data => {
        if (cancelled) return
        setJob(data); setLoading(false)
        if (TERMINAL.has(data.status)) {
          getJobParts(jobId).then(p => { if (!cancelled) setParts(p) }).catch(() => {})
        }
      })
      .catch(err => { if (!cancelled) { setError(err.message ?? 'Không tải được job'); setLoading(false) } })
    return () => { cancelled = true }
  }, [jobId])

  async function handleRetry() {
    if (!job || actionLoading) return
    setActionLoading(true)
    try {
      await retryRender(jobId)
      addNotification({ title: 'Retry started', type: 'success' })
      const updated = await getJob(jobId)
      setJob(updated)
    } catch (e) {
      addNotification({ title: e instanceof ApiError ? e.message : 'Retry failed', type: 'error' })
    } finally { setActionLoading(false) }
  }

  async function handleRerun() {
    if (!job || actionLoading) return
    setActionLoading(true)
    try {
      await resumeRender(jobId)
      addNotification({ title: 'Re-run started', type: 'success' })
      const updated = await getJob(jobId)
      setJob(updated)
    } catch (e) {
      addNotification({ title: e instanceof ApiError ? e.message : 'Re-run failed', type: 'error' })
    } finally { setActionLoading(false) }
  }

  async function handleDelete() {
    const choice = await confirmDialog({
      title: 'Xóa job này?',
      message: 'Job và tất cả file output sẽ bị xóa. Thao tác không thể hoàn tác.',
      buttons: [
        { id: 'delete', label: 'Xóa', variant: 'danger' },
        { id: 'cancel', label: 'Hủy' },
      ],
    })
    if (choice !== 'delete') return
    setActionLoading(true)
    try {
      await deleteJob(jobId, true)
      addNotification({ title: 'Job đã xóa', type: 'success' })
      onClose()
    } catch (e) {
      addNotification({ title: e instanceof ApiError ? e.message : 'Xóa thất bại', type: 'error' })
      setActionLoading(false)
    }
  }

  async function handlePlayerFeedback(partNo: number, rating: 1 | -1, part: JobPart) {
    const current = fbRatings[partNo]
    const newRating = current === rating ? null : rating
    setFbRatings((prev) => ({ ...prev, [partNo]: newRating }))
    try {
      if (newRating === null) await deleteClipFeedback(jobId, partNo)
      else await submitClipFeedback(jobId, partNo, {
        rating: newRating, goal: '', channel_code: '', hook_type: 'none',
        clip_type: 'unknown', start_sec: 0,
        end_sec: part.duration ?? 0, duration_sec: part.duration ?? 0,
      })
    } catch { /* fire-and-forget */ }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)', fontSize: 12 }}>
        Đang tải…
      </div>
    )
  }

  if (error || !job) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8 }}>
        <div style={{ fontSize: 11, color: 'var(--fail)' }}>{error ?? 'Job không tìm thấy'}</div>
        <button onClick={onClose} style={{ fontSize: 10, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer' }}>Đóng</button>
      </div>
    )
  }

  const st = STATUS_CFG[job.status] ?? FALLBACK_ST
  const meta = parseMeta(job.payload_json)
  const bestPartNo = parseBestPartNo(job.result_json)
  const doneParts = parts.filter(p => p.status === 'done')
  const failedParts = parts.filter(p => p.status === 'failed')
  const outputDir = doneParts[0]?.output_file
    ? (() => { const f = doneParts[0].output_file; const sep = f.includes('\\') ? '\\' : '/'; return f.substring(0, f.lastIndexOf(sep)) })()
    : (job as unknown as { output_dir?: string | null }).output_dir

  const canRetry  = ['completed_with_errors', 'partial', 'failed'].includes(job.status) && failedParts.length > 0
  const canRerun  = TERMINAL.has(job.status)
  const canEditor = ['completed', 'partial', 'completed_with_errors'].includes(job.status)

  return (
    <div data-testid="job-detail-drawer" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Header ── */}
      <div style={{
        padding: '14px 18px 12px', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 700, color: 'var(--text-1)',
              fontFamily: 'var(--fh)', letterSpacing: '.3px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {(job as unknown as { title?: string }).title || job.job_id.slice(0, 16)}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
                background: st.color + '20', color: st.color,
                border: `1px solid ${st.color}40`,
                fontFamily: 'var(--fh)', letterSpacing: '.4px',
              }}>{st.label}</span>
              {doneParts.length > 0 && (
                <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{doneParts.length} clip xong</span>
              )}
              {failedParts.length > 0 && (
                <span style={{ fontSize: 9, color: 'var(--fail)' }}>{failedParts.length} lỗi</span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            data-testid="drawer-close-btn"
            style={{
              flexShrink: 0, fontSize: 14, background: 'none', border: 'none',
              color: 'var(--text-3)', cursor: 'pointer', padding: '2px 4px', lineHeight: 1,
            }}
          >✕</button>
        </div>

        {/* Meta row */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {meta.platform && <MetaChip label="Platform" value={meta.platform} />}
          {meta.ratio    && <MetaChip label="Ratio"    value={meta.ratio}    />}
          <MetaChip label="Tạo lúc" value={formatDateTime(job.created_at)} />
          <MetaChip label="Job ID"  value={job.job_id.slice(0, 10) + '…'}  />
        </div>
      </div>

      {/* ── Action bar ── */}
      <div style={{
        padding: '8px 18px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)', flexShrink: 0,
        display: 'flex', gap: 6, flexWrap: 'wrap',
      }}>
        {outputDir && (
          <button onClick={() => window.electronAPI?.openPath?.(outputDir)} style={actionBtnStyle('var(--text-2)')}>
            <IconFolder size={12} /> Mở thư mục
          </button>
        )}
        {canEditor && (
          <button onClick={() => { openEditor(jobId, 1); setActivePanel('editor') }} style={actionBtnStyle('var(--accent)')}>
            ✏ Chỉnh sửa
          </button>
        )}
        {canRetry && (
          <button onClick={handleRetry} disabled={actionLoading} style={actionBtnStyle('var(--warn)')}>
            {actionLoading ? '…' : '↺ Retry Failed'}
          </button>
        )}
        {canRerun && !canRetry && (
          <button onClick={handleRerun} disabled={actionLoading} style={actionBtnStyle('var(--text-2)')}>
            {actionLoading ? '…' : '⟳ Render lại'}
          </button>
        )}
        <button onClick={handleDelete} disabled={actionLoading} style={{ ...actionBtnStyle('var(--fail)'), marginLeft: 'auto', borderColor: 'rgba(232,64,122,.3)', background: 'rgba(232,64,122,.07)' }}>
          <IconX size={12} /> Xóa
        </button>
      </div>

      {/* ── Content ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Clip gallery */}
        {parts.length > 0 && (
          <section>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '.08em', textTransform: 'uppercase', marginBottom: 10 }}>
              Clips — {parts.length} total
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))', gap: 8 }}>
              {[...parts]
                .sort((a, b) => {
                  if (a.status === 'done' && b.status !== 'done') return -1
                  if (b.status === 'done' && a.status !== 'done') return 1
                  const sa = a.viral_score || a.hook_score || 0
                  const sb = b.viral_score || b.hook_score || 0
                  return sb - sa
                })
                .map(part => (
                  <ClipCard
                    key={part.part_no}
                    part={part}
                    isBest={part.part_no === bestPartNo}
                    jobId={jobId}
                    onPlay={() => {
                      const idx = doneParts.findIndex((d) => d.part_no === part.part_no)
                      if (idx >= 0) setPlayerIdx(idx)
                    }}
                  />
                ))
              }
            </div>
          </section>
        )}

        {playerIdx !== null && doneParts.length > 0 && (
          <ClipPlayerModal
            jobId={jobId}
            parts={doneParts}
            index={Math.min(playerIdx, doneParts.length - 1)}
            onNavigate={setPlayerIdx}
            onClose={() => setPlayerIdx(null)}
            partScores={{}}
            partRanks={{}}
            feedbackRatings={fbRatings}
            onFeedback={handlePlayerFeedback}
            t={tRender}
          />
        )}

        {/* Progress bar (non-terminal) */}
        {!TERMINAL.has(job.status) && (
          <section>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Tiến độ
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1, height: 4, borderRadius: 99, background: 'var(--bg-hover)', overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 99,
                  width: `${job.progress_percent}%`,
                  background: 'linear-gradient(90deg, var(--accent), var(--accent)88)',
                  transition: 'width .4s ease',
                }} />
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', flexShrink: 0 }}>
                {job.progress_percent}%
              </span>
            </div>
            {job.message && (
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 4 }}>{job.message}</div>
            )}
          </section>
        )}

        {/* AI Summary */}
        {TERMINAL.has(job.status) && (
          <AiSummaryCard payloadJson={job.payload_json} resultJson={job.result_json} />
        )}

        {/* Error message for failed jobs */}
        {job.status === 'failed' && job.message && (
          <section>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-3)', letterSpacing: '.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Lỗi
            </div>
            <pre style={{
              fontSize: 9, color: 'var(--fail)', background: 'rgba(232,64,122,.06)',
              border: '1px solid rgba(232,64,122,.18)', borderRadius: 6,
              padding: '8px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            }}>
              {job.message}
            </pre>
          </section>
        )}
      </div>
    </div>
  )
}

function actionBtnStyle(color: string): React.CSSProperties {
  return {
    fontSize: 10, fontWeight: 700, padding: '4px 11px', borderRadius: 6,
    border: '1px solid var(--border)', background: 'var(--bg-hover)',
    color, cursor: 'pointer', fontFamily: 'var(--fb)',
  }
}
