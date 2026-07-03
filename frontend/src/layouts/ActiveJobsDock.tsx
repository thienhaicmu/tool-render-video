/**
 * ActiveJobsDock — persistent bottom strip listing running/queued jobs.
 *
 * Mounted globally so a user who navigates away from the render workflow
 * still sees live progress + a cancel control. Subscribes via
 * `useActiveJobs()` which arms the shared 4 s `/api/jobs/history` poll.
 *
 * Click a row → jump to Clip Studio with the job attached (RenderWorkflow
 * auto-reattach in StepRendering already consumes `renderStore.activeJobId`).
 */
import React, { useState, useEffect } from 'react'
import { useActiveJobs, useJobsStore } from '../stores/jobsStore'
import { useUIStore } from '../stores/uiStore'
import { useRenderStore } from '../stores/renderStore'
import { useI18n } from '../i18n/useI18n'
import { cancelRender, retryRender, resumeRender } from '../api/render'
import { moveJobToTop, moveJobToBottom } from '../api/jobs'
import { cancelJob as cancelDownloadJob } from '../api/platformDownloader'
import { IconQueue, IconToTop, IconToBottom, IconX } from '../components/icons'
import type { HistoryItem } from '../types/api'

const MAX_VISIBLE = 3

// P1.4 — "needs attention": terminal-failed/interrupted render jobs stay
// in the dock for this long (unless dismissed) so a failure that happens
// while the user is on another screen doesn't vanish with its toast.
const ATTENTION_WINDOW_MS = 30 * 60 * 1000
const DISMISSED_KEY = 'dock_dismissed_attention_v1'

function loadDismissed(): Set<string> {
  try {
    const raw = sessionStorage.getItem(DISMISSED_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch { return new Set() }
}
function saveDismissed(ids: Set<string>) {
  try { sessionStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids])) } catch { /* ignore */ }
}


export function ActiveJobsDock() {
  const { items, refresh } = useActiveJobs()
  const queueOrder = useJobsStore((s) => s.queueOrder)
  const { t } = useI18n()
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)

  // P1.4 — session-scoped dismissals for the attention section.
  const [dismissed, setDismissed] = useState<Set<string>>(loadDismissed)
  function dismiss(jobId: string) {
    setDismissed((prev) => {
      const next = new Set(prev).add(jobId)
      saveDismissed(next)
      return next
    })
  }

  const activeItems = items.filter(
    (j) => j.status === 'running' || j.status === 'queued',
  )

  // P1.4 — recently failed/interrupted renders. Previously these dropped
  // out of the dock the instant they turned terminal, so a failure that
  // happened while the user was on another screen was only discoverable
  // via a 5 s toast or by opening Library.
  const now = Date.now()
  const attentionItems = items.filter((j) => {
    if (j.kind !== 'render') return false
    if (j.status !== 'failed' && j.status !== 'interrupted') return false
    if (dismissed.has(j.job_id)) return false
    const ts = Date.parse(j.updated_at || '')
    return !Number.isNaN(ts) && now - ts < ATTENTION_WINDOW_MS
  }).slice(0, 2)

  const hasContent = activeItems.length > 0 || attentionItems.length > 0

  // The dock is a fixed bottom strip mounted as a sibling of the app shell.
  // Without reserving space it would overlap the bottom of the content (the
  // workflow's action footer + status bar). Publish its height as a CSS var
  // so the shell (`.cs-root`) can shrink from the bottom by exactly that much.
  // Height is constant (one 40px row + 8px padding top/bottom + 1px border).
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--active-jobs-dock-h', hasContent ? '57px' : '0px')
    return () => { root.style.setProperty('--active-jobs-dock-h', '0px') }
  }, [hasContent])

  if (!hasContent) return null

  const visible = activeItems.slice(0, MAX_VISIBLE)
  const overflow = activeItems.length - visible.length

  function handleOpen(job: HistoryItem) {
    if (job.kind === 'render') {
      useRenderStore.setState((state) => ({
        activeJobId: job.job_id,
        jobs: state.jobs[job.job_id]
          ? state.jobs
          : {
              ...state.jobs,
              [job.job_id]: {
                job_id: job.job_id,
                kind: 'render',
                status: job.status,
                stage: job.stage,
                progress_percent: job.progress_percent,
                message: job.message,
                payload_json: '',
                result_json: '',
                created_at: job.created_at,
                updated_at: job.updated_at,
              } as never,
            },
      }))
      // Pha 4 — explicit "open this job's Monitor". RenderWorkflow consumes
      // monitorJobId (Step 3); ClipStudio flips to the Render tab.
      setMonitorJobId(job.job_id)
      setActivePanel('clip-studio')
    } else {
      setActivePanel('download')
    }
  }

  async function handleCancel(job: HistoryItem) {
    try {
      if (job.kind === 'render') await cancelRender(job.job_id)
      else await cancelDownloadJob(job.job_id)
      void refresh()
    } catch (_err) {
      // Cancel errors are surfaced by the screen-level toast; the dock
      // stays silent to avoid duplicate notifications.
    }
  }

  // Pha 3 — bump a queued render to the front of the dispatch queue, then
  // refresh so the new position shows without waiting for the 4 s poll.
  async function handleMoveTop(job: HistoryItem) {
    try {
      await moveJobToTop(job.job_id)
      void refresh()
    } catch (_err) {
      // 404 = job already started / finished between poll + click — ignore.
    }
  }

  // Pha 3.2 — send a queued render to the back of the dispatch queue.
  async function handleMoveBottom(job: HistoryItem) {
    try {
      await moveJobToBottom(job.job_id)
      void refresh()
    } catch (_err) {
      // 404 = no longer pending — ignore.
    }
  }

  return (
    <div
      style={{
        ...styles.dock,
        // P2.1 single-shell: the slim rail is always visible, so the dock
        // always starts at its right edge.
        left: 'var(--sidebar-width, 0px)',
      }}
      role="region"
      aria-label="Active jobs"
    >
      <div style={styles.inner}>
        {attentionItems.map((job) => (
          <AttentionRow
            key={job.job_id}
            job={job}
            onOpen={handleOpen}
            onDismiss={dismiss}
            onActed={() => void refresh()}
          />
        ))}
        {visible.map((job) => (
          <DockRow
            key={job.job_id}
            job={job}
            queueOrder={queueOrder}
            onOpen={handleOpen}
            onCancel={handleCancel}
            onMoveTop={handleMoveTop}
            onMoveBottom={handleMoveBottom}
          />
        ))}
        {overflow > 0 && (
          <button
            style={styles.overflow}
            onClick={() => setActivePanel('queue')}
            title={t('queue_manage')}
          >
            +{overflow} {t('dock_running_suffix')}
          </button>
        )}
        {/* Pha 3.3a — always-present entry point to the full queue drawer. */}
        <button
          style={styles.manage}
          onClick={() => setActivePanel('queue')}
          title={t('queue_manage')}
          aria-label={t('queue_manage')}
        >
          <IconQueue size={16} />
        </button>
      </div>
    </div>
  )
}

// P1.4 — a failed/interrupted render pinned in the dock with inline
// recovery. Retry restarts a failed job; Resume continues an interrupted
// one. Dismiss (×) hides it for this session only.
function AttentionRow({ job, onOpen, onDismiss, onActed }: {
  job: HistoryItem
  onOpen: (job: HistoryItem) => void
  onDismiss: (jobId: string) => void
  onActed: () => void
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const isInterrupted = job.status === 'interrupted'
  const title = job.title || job.source_hint || job.job_id.slice(0, 8)

  async function handleRecover(e: React.MouseEvent) {
    e.stopPropagation()
    if (busy) return
    setBusy(true)
    try {
      if (isInterrupted) await resumeRender(job.job_id)
      else await retryRender(job.job_id)
      onDismiss(job.job_id)
      onActed()
    } catch {
      // Job may have been retried elsewhere / deleted — next poll reconciles.
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ ...styles.row, borderColor: 'rgba(239,68,68,.35)' }}>
      <button style={styles.rowBody} onClick={() => onOpen(job)} title={t('dock_open_detail')}>
        <span style={{
          ...styles.kindBadge,
          backgroundColor: 'var(--status-error-bg, rgba(239,68,68,.12))',
          color: 'var(--status-error)',
        }}>
          {isInterrupted ? t('dock_interrupted') : t('dock_failed')}
        </span>
        <span style={styles.rowText}>
          <span style={styles.rowTitle}>{title}</span>
          <span style={styles.rowSubtitle}>{job.message || job.stage || ''}</span>
        </span>
        <span />
        <span style={{ ...styles.pct, color: 'var(--status-error)' }} />
      </button>
      <button
        style={{ ...styles.moveBtn, width: 'auto', padding: '0 10px', fontSize: 11, fontWeight: 600 }}
        onClick={handleRecover}
        disabled={busy}
        title={isInterrupted ? t('dock_resume') : t('dock_retry')}
      >
        {busy ? '…' : isInterrupted ? t('dock_resume') : t('dock_retry')}
      </button>
      <button
        style={styles.cancelBtn}
        onClick={(e) => { e.stopPropagation(); onDismiss(job.job_id) }}
        title={t('dock_dismiss')}
        aria-label={t('dock_dismiss')}
      >
        <IconX size={13} />
      </button>
    </div>
  )
}

function DockRow({
  job,
  queueOrder,
  onOpen,
  onCancel,
  onMoveTop,
  onMoveBottom,
}: {
  job: HistoryItem
  queueOrder: string[]
  onOpen: (job: HistoryItem) => void
  onCancel: (job: HistoryItem) => void
  onMoveTop: (job: HistoryItem) => void
  onMoveBottom: (job: HistoryItem) => void
}) {
  const { t } = useI18n()
  const [hovered, setHovered] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [moving, setMoving] = useState(false)

  const pct = Math.max(0, Math.min(100, job.progress_percent || 0))
  const isQueued = job.status === 'queued'
  const kindLabel = job.kind === 'render' ? 'RENDER' : 'DOWNLOAD'
  const kindBg = job.kind === 'render' ? 'var(--accent-subtle)' : 'rgba(34, 197, 94, 0.12)'
  const kindFg = job.kind === 'render' ? 'var(--accent-primary)' : 'rgb(34, 197, 94)'
  const title = job.title || job.source_hint || job.job_id.slice(0, 8)
  // Pha 3 — position in the dispatch queue (render jobs only; downloads
  // run on a separate engine and aren't in queueOrder → posIdx === -1).
  const posIdx = isQueued ? queueOrder.indexOf(job.job_id) : -1
  const queueTotal = queueOrder.length
  const canMoveTop = posIdx > 0                       // already #1 → nothing to bump
  const canMoveBottom = posIdx >= 0 && posIdx < queueTotal - 1  // already last → nothing
  const subtitle = isQueued
    ? (posIdx >= 0 ? `${t('dock_queued')} · #${posIdx + 1}/${queueTotal}` : t('dock_queued'))
    : job.message || job.stage || t('dock_processing')

  return (
    <div
      style={{
        ...styles.row,
        backgroundColor: hovered ? 'var(--surface-card-hover)' : 'var(--surface-card)',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        style={styles.rowBody}
        onClick={() => onOpen(job)}
        title={t('dock_open_detail')}
      >
        <span style={{ ...styles.kindBadge, backgroundColor: kindBg, color: kindFg }}>
          {kindLabel}
        </span>
        <span style={styles.rowText}>
          <span style={styles.rowTitle}>{title}</span>
          <span style={styles.rowSubtitle}>{subtitle}</span>
        </span>
        <span style={styles.progressWrap} aria-label={`${pct}%`}>
          <span style={{ ...styles.progressBar, width: `${pct}%` }} />
        </span>
        <span style={styles.pct}>{isQueued ? 'queued' : `${Math.round(pct)}%`}</span>
      </button>
      {canMoveTop && (
        <button
          style={styles.moveBtn}
          onClick={async (e) => {
            e.stopPropagation()
            if (moving) return
            setMoving(true)
            await onMoveTop(job)
            setMoving(false)
          }}
          disabled={moving}
          title={t('dock_move_top')}
          aria-label={t('dock_move_top')}
        >
          {moving ? '…' : <IconToTop size={13} />}
        </button>
      )}
      {canMoveBottom && (
        <button
          style={styles.moveBtn}
          onClick={async (e) => {
            e.stopPropagation()
            if (moving) return
            setMoving(true)
            await onMoveBottom(job)
            setMoving(false)
          }}
          disabled={moving}
          title={t('dock_move_bottom')}
          aria-label={t('dock_move_bottom')}
        >
          {moving ? '…' : <IconToBottom size={13} />}
        </button>
      )}
      <button
        style={styles.cancelBtn}
        onClick={async (e) => {
          e.stopPropagation()
          if (cancelling) return
          setCancelling(true)
          await onCancel(job)
          setCancelling(false)
        }}
        disabled={cancelling}
        title={t('dock_cancel_job')}
        aria-label={t('dock_cancel')}
      >
        {cancelling ? '…' : <IconX size={13} />}
      </button>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  dock: {
    position: 'fixed',
    bottom: 0,
    right: 0,
    backgroundColor: 'var(--surface-panel)',
    borderTop: '1px solid var(--border-subtle)',
    boxShadow: '0 -4px 12px rgba(0,0,0,0.06)',
    zIndex: 1000,
    pointerEvents: 'auto',
  },
  inner: {
    display: 'flex',
    gap: '8px',
    padding: '8px 12px',
    overflowX: 'auto',
    alignItems: 'center',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    height: 40,
    borderRadius: 8,
    border: '1px solid var(--border-subtle)',
    overflow: 'hidden',
    minWidth: 320,
    maxWidth: 420,
    flexShrink: 0,
    transition: 'background-color 0.12s ease',
  },
  rowBody: {
    flex: 1,
    display: 'grid',
    gridTemplateColumns: 'auto 1fr 80px auto',
    gap: 10,
    alignItems: 'center',
    padding: '0 10px',
    height: '100%',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    color: 'var(--text-primary)',
    textAlign: 'left',
    minWidth: 0,
  },
  kindBadge: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '0.06em',
    padding: '2px 6px',
    borderRadius: 4,
    whiteSpace: 'nowrap',
  },
  rowText: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    minWidth: 0,
    overflow: 'hidden',
  },
  rowTitle: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  rowSubtitle: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  progressWrap: {
    position: 'relative',
    height: 4,
    width: 80,
    backgroundColor: 'var(--border-subtle)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressBar: {
    position: 'absolute',
    inset: 0,
    backgroundColor: 'var(--accent-primary)',
    transition: 'width 0.3s ease',
  },
  pct: {
    fontSize: 10,
    color: 'var(--text-secondary)',
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  cancelBtn: {
    width: 32,
    height: '100%',
    border: 'none',
    borderLeft: '1px solid var(--border-subtle)',
    background: 'transparent',
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 16,
    lineHeight: 1,
  },
  // Pha 3 — move-to-top control for queued jobs (accent-toned to read as
  // a positive action vs the cancel ×).
  moveBtn: {
    width: 30,
    height: '100%',
    border: 'none',
    borderLeft: '1px solid var(--border-subtle)',
    background: 'transparent',
    color: 'var(--accent-primary)',
    cursor: 'pointer',
    fontSize: 15,
    lineHeight: 1,
  },
  overflow: {
    flexShrink: 0,
    height: 40,
    padding: '0 12px',
    border: '1px dashed var(--border-subtle)',
    borderRadius: 8,
    background: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
  },
  manage: {
    flexShrink: 0,
    width: 40,
    height: 40,
    border: '1px solid var(--border-subtle)',
    borderRadius: 8,
    background: 'transparent',
    color: 'var(--accent-primary)',
    fontSize: 16,
    cursor: 'pointer',
  },
}
