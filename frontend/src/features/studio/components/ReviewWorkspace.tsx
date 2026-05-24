import { useState, useEffect } from 'react'
import { AIChip } from '../../../components/ui/AIChip'
import { type ReviewCardData, type ReviewCardStatus } from '../types'
import { getJobHistory, getJobParts } from '../../../api/jobs'
import { mapPartsToReviewCards } from '../../../adapters/studioAdapters'
import { BASE_URL } from '../../../api/client'
import { apiFetch } from '../../../api/client'
import type { JobPart } from '../../../types/api'

// ── Thumbnail URL ──────────────────────────────────────────────────────────────

function thumbnailUrl(jobId: string, partNo: number): string {
  return `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/thumbnail?t=0.5&w=320`
}

// ── Export endpoint ───────────────────────────────────────────────────────────

const EXPORT_API_PATH = (jobId: string, partNo: number) =>
  `/api/jobs/${jobId}/parts/${partNo}/export`

// ── Score colors ──────────────────────────────────────────────────────────────

function scoreColor(val: number): string {
  if (val >= 70) return 'var(--score-high, #34C878)'
  if (val >= 40) return 'var(--score-mid, #F5A623)'
  return 'var(--score-low, #E05252)'
}

// ── ClipCard ──────────────────────────────────────────────────────────────────

interface ClipCardProps {
  card: ReviewCardData
  status: ReviewCardStatus
  jobId: string | null
  partNo: number
  sessionOutputDir: string
  onApprove: () => void
  onReject: () => void
  onRestore: () => void
}

function ClipCard({ card, status, jobId, partNo, sessionOutputDir, onApprove, onReject, onRestore }: ClipCardProps) {
  const [downloading, setDownloading] = useState(false)
  const [downloadDone, setDownloadDone] = useState(false)
  const [downloadErr, setDownloadErr] = useState<string | null>(null)
  const [thumbError, setThumbError] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [exportPath, setExportPath] = useState<string | null>(null)

  const handleExport = async () => {
    if (!jobId) return
    setDownloading(true)
    setDownloadErr(null)

    // Determine save directory: use a native picker if available, else sessionOutputDir or default
    let destDir = sessionOutputDir || 'exports'
    const api = (window as any).electronAPI
    if (api?.pickOutputDir) {
      const picked = await api.pickOutputDir()
      if (picked) destDir = picked
    }

    try {
      const res: any = await apiFetch(EXPORT_API_PATH(jobId, partNo), {
        method: 'POST',
        body: JSON.stringify({ destination_dir: destDir }),
      })
      setDownloadDone(true)
      setExportPath(res?.path ?? res?.dest ?? null)
    } catch (err: any) {
      setDownloadErr(err?.detail?.toString() ?? err?.message ?? 'Export failed')
    } finally {
      setDownloading(false)
    }
  }

  const openExportFolder = async () => {
    const api = (window as any).electronAPI
    const path = exportPath || sessionOutputDir
    if (api?.openPath && path) await api.openPath(path)
  }

  const isRejected = status === 'rejected'
  const isApproved = status === 'approved'
  const thumbSrc = jobId ? thumbnailUrl(jobId, partNo) : null

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        ...cs.card,
        borderColor: isApproved
          ? 'var(--status-success)'
          : isRejected
          ? 'var(--border-subtle)'
          : hovered
          ? 'var(--border-strong)'
          : 'var(--border-default)',
        opacity: isRejected ? 0.45 : 1,
        transform: hovered && !isRejected ? 'translateY(-2px)' : 'none',
        boxShadow: hovered && !isRejected ? '0 6px 24px rgba(0,0,0,0.55)' : '0 1px 3px rgba(0,0,0,0.45)',
        transition: 'border-color 0.15s ease, opacity 0.2s ease, transform 0.15s ease, box-shadow 0.15s ease',
      }}
    >
      {/* Thumbnail */}
      <div style={cs.thumbWrap}>
        <div style={cs.thumbAspect}>
          <div style={cs.thumbInner}>
            {thumbSrc && !thumbError ? (
              <img
                src={thumbSrc}
                alt={card.clipLabel}
                onError={() => setThumbError(true)}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <span style={cs.thumbPlaceholder}>▶</span>
            )}
          </div>
        </div>

        {/* Score overlay — only if scored */}
        {card.confidence > 0 && (
          <div style={cs.scoreOverlay}>
            <span style={{ ...cs.scoreNum, color: scoreColor(card.confidence) }}>
              {card.confidence}
            </span>
            <span style={{ ...cs.scoreLabel, color: scoreColor(card.confidence) }}>
              {card.confidence >= 70 ? 'HIGH' : card.confidence >= 40 ? 'MED' : 'LOW'}
            </span>
          </div>
        )}

        {isApproved && <div style={cs.approvedBadge}>✓ Selected</div>}
      </div>

      {/* Info */}
      <div style={cs.info}>
        <div style={cs.infoTop}>
          <span style={cs.clipLabel}>{card.clipLabel}</span>
          <AIChip variant="applied" label="AI" />
        </div>
        <p style={cs.fileName}>{card.reasoning}</p>
        <span style={cs.impact}>{card.impact}</span>
      </div>

      {/* Actions */}
      <div style={cs.actions}>
        {isRejected ? (
          <button onClick={onRestore} style={{ ...cs.btn, ...cs.restoreBtn }}>↩ Restore</button>
        ) : (
          <>
            <button
              onClick={isApproved ? onRestore : onApprove}
              style={{ ...cs.btn, flex: 1, ...(isApproved ? cs.approvedBtn : cs.approveBtn) }}
            >
              {isApproved ? '✓ Selected' : '✓ Select'}
            </button>
            <button onClick={onReject} style={{ ...cs.btn, width: '30px', ...cs.rejectBtn }}>✕</button>
          </>
        )}

        {downloadDone ? (
          <button onClick={openExportFolder} style={{ ...cs.btn, ...cs.openBtn }}>
            📂 Open
          </button>
        ) : (
          <button
            onClick={handleExport}
            disabled={downloading}
            style={{ ...cs.btn, ...cs.saveBtn, opacity: downloading ? 0.6 : 1 }}
          >
            {downloading ? '⏳' : '⬇ Save'}
          </button>
        )}
      </div>

      {downloadErr && (
        <span style={cs.exportErr}>{downloadErr}</span>
      )}
    </div>
  )
}

// ── ReviewWorkspace ───────────────────────────────────────────────────────────

interface ReviewWorkspaceProps {
  sessionOutputDir?: string
}

export function ReviewWorkspace({ sessionOutputDir = '' }: ReviewWorkspaceProps) {
  const [statuses, setStatuses] = useState<Record<string, ReviewCardStatus>>({})
  const [cards, setCards] = useState<ReviewCardData[]>([])
  const [reviewLoading, setReviewLoading] = useState(true)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)

  useEffect(() => {
    getJobHistory(5, 0)
      .then((res) => {
        const completedJob = res.items.find(
          (item) => item.status === 'completed' || item.status === 'completed_with_errors',
        )
        if (!completedJob) {
          setReviewError('No completed render found. Submit a render first.')
          return null
        }
        setJobId(completedJob.job_id)
        return getJobParts(completedJob.job_id)
      })
      .then((parts: JobPart[] | null) => {
        if (!parts) return
        const mapped = mapPartsToReviewCards(parts)
        setCards(mapped)
        if (mapped.length === 0) {
          setReviewError('No completed clips found for the latest render.')
        }
      })
      .catch(() => {
        setReviewError('Failed to load render results.')
      })
      .finally(() => setReviewLoading(false))
  }, [])

  const getStatus = (id: string): ReviewCardStatus => statuses[id] ?? 'pending'
  const approvedCount = cards.filter((c) => getStatus(c.id) === 'approved').length

  const handleExportAll = async () => {
    if (!jobId) return
    const approved = cards.filter((c) => getStatus(c.id) === 'approved')
    let destDir = sessionOutputDir || 'exports'
    const api = (window as any).electronAPI
    if (api?.pickOutputDir) {
      const picked = await api.pickOutputDir()
      if (picked) destDir = picked
    }
    await Promise.allSettled(
      approved.map((c) =>
        fetch(EXPORT_API_PATH(jobId, parseInt(c.id)), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ destination_dir: destDir }),
        }),
      ),
    )
  }

  // Loading
  if (reviewLoading) {
    return (
      <div style={ws.loadingPage}>
        <div style={ws.loadingText}>Loading render results…</div>
      </div>
    )
  }

  // Error / no data
  if (reviewError && cards.length === 0) {
    return (
      <div style={ws.loadingPage}>
        <div style={{ textAlign: 'center' as const, display: 'flex', flexDirection: 'column' as const, gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '32px', opacity: 0.3 }}>🎬</span>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{reviewError}</span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            Complete a render job to see your clips here.
          </span>
        </div>
      </div>
    )
  }

  return (
    <div style={ws.page}>
      {/* Summary bar */}
      <div style={ws.summaryBar}>
        <div style={ws.summaryLeft}>
          <AIChip variant="applied" label="AI Director" />
          <span style={ws.statChip}>{cards.length} clips</span>
          {jobId && (
            <span style={{ ...ws.statChip, fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
              {jobId.slice(0, 8)}…
            </span>
          )}
        </div>
        <div style={ws.summaryRight}>
          <span style={ws.approvedText}>{approvedCount}/{cards.length} selected</span>
          <button
            onClick={handleExportAll}
            disabled={approvedCount === 0}
            style={{
              ...ws.exportAllBtn,
              opacity: approvedCount === 0 ? 0.4 : 1,
              cursor: approvedCount === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            ⬇ Export Selected
          </button>
        </div>
      </div>

      {/* Clip grid */}
      <div style={ws.grid}>
        {cards.map((card) => (
          <ClipCard
            key={card.id}
            card={card}
            status={getStatus(card.id)}
            jobId={jobId}
            partNo={parseInt(card.id)}
            sessionOutputDir={sessionOutputDir}
            onApprove={() => setStatuses((p) => ({ ...p, [card.id]: 'approved' }))}
            onReject={() => setStatuses((p) => ({ ...p, [card.id]: 'rejected' }))}
            onRestore={() => setStatuses((p) => ({ ...p, [card.id]: 'pending' }))}
          />
        ))}
      </div>

      {/* Footer */}
      <div style={{
        ...ws.footer,
        borderTopColor: approvedCount > 0 ? 'var(--status-success)' : 'var(--border-subtle)',
        backgroundColor: approvedCount > 0 ? 'var(--status-success-bg)' : 'var(--surface-card)',
      }}>
        <span style={{ fontSize: 'var(--text-sm)', color: approvedCount > 0 ? 'var(--status-success)' : 'var(--text-secondary)', fontWeight: 500 }}>
          {approvedCount > 0 ? `${approvedCount} clip${approvedCount > 1 ? 's' : ''} selected` : `0 of ${cards.length} selected`}
        </span>
        <span style={{ fontSize: 'var(--text-xs)', color: approvedCount > 0 ? 'var(--status-success)' : 'var(--text-tertiary)' }}>
          {approvedCount > 0 ? '✓ Ready to export' : 'Select clips to export'}
        </span>
      </div>
    </div>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const ws: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: 'var(--surface-base)',
  },
  loadingPage: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--surface-base)',
  },
  loadingText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
  },
  summaryBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-3) var(--space-6)',
    backgroundColor: 'var(--surface-card)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    flexWrap: 'wrap' as const,
    gap: 'var(--space-3)',
  },
  summaryLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
    flexWrap: 'wrap' as const,
  },
  summaryRight: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  statChip: {
    display: 'inline-flex',
    alignItems: 'center',
    height: '22px',
    padding: '0 var(--space-2)',
    borderRadius: 'var(--radius-sm)',
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-xs)',
    border: '1px solid var(--border-subtle)',
  },
  approvedText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  exportAllBtn: {
    height: '32px',
    padding: '0 var(--space-4)',
    border: 'none',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'opacity 0.15s ease',
  },
  grid: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-5) var(--space-6)',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: 'var(--space-4)',
    alignContent: 'start',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-3) var(--space-6)',
    borderTop: '1px solid',
    flexShrink: 0,
    transition: 'background-color 0.3s ease, border-color 0.3s ease',
  },
}

const cs: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--surface-card)',
    border: '1px solid',
    borderRadius: '12px',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  },
  thumbWrap: {
    position: 'relative',
    backgroundColor: '#0A0C11',
  },
  thumbAspect: {
    paddingTop: '177.78%',
    position: 'relative',
  },
  thumbInner: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  thumbPlaceholder: {
    fontSize: '28px',
    color: 'rgba(255,255,255,0.15)',
  },
  scoreOverlay: {
    position: 'absolute',
    bottom: 'var(--space-2)',
    right: 'var(--space-2)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    backgroundColor: 'rgba(13,15,20,0.88)',
    borderRadius: '6px',
    padding: '3px 6px',
  },
  scoreNum: {
    fontSize: '20px',
    fontWeight: 700,
    lineHeight: 1.1,
  },
  scoreLabel: {
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.06em',
  },
  approvedBadge: {
    position: 'absolute',
    top: 'var(--space-2)',
    left: 'var(--space-2)',
    backgroundColor: 'var(--status-success)',
    color: '#fff',
    fontSize: '10px',
    fontWeight: 700,
    padding: '2px 6px',
    borderRadius: '4px',
  },
  info: {
    padding: 'var(--space-3)',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    flex: 1,
  },
  infoTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 'var(--space-2)',
  },
  clipLabel: {
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  fileName: {
    margin: 0,
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  impact: {
    fontSize: 'var(--text-xs)',
    color: 'var(--status-success)',
  },
  actions: {
    display: 'flex',
    gap: '6px',
    padding: 'var(--space-2) var(--space-3) var(--space-3)',
  },
  btn: {
    height: '30px',
    borderRadius: '6px',
    fontSize: '12px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'opacity 0.15s ease',
    border: 'none',
    padding: '0 var(--space-2)',
  },
  approveBtn: {
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-default)',
  },
  approvedBtn: {
    backgroundColor: 'var(--status-success-bg)',
    color: 'var(--status-success)',
    border: '1px solid rgba(52,200,120,0.3)',
  },
  rejectBtn: {
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-tertiary)',
    border: '1px solid var(--border-subtle)',
  },
  restoreBtn: {
    flex: 1,
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-tertiary)',
    border: '1px solid var(--border-subtle)',
  },
  saveBtn: {
    padding: '0 var(--space-3)',
    flexShrink: 0,
    fontWeight: 700,
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
  },
  openBtn: {
    padding: '0 var(--space-2)',
    flexShrink: 0,
    backgroundColor: 'var(--status-success-bg)',
    color: 'var(--status-success)',
    border: '1px solid rgba(52,200,120,0.3)',
  },
  exportErr: {
    fontSize: '10px',
    color: 'var(--status-error)',
    padding: '0 var(--space-3) var(--space-2)',
  },
}
