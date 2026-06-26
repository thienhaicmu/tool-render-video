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
import React, { useState } from 'react'
import { useActiveJobs } from '../stores/jobsStore'
import { useUIStore } from '../stores/uiStore'
import { useRenderStore } from '../stores/renderStore'
import { useI18n } from '../i18n/useI18n'
import { cancelRender } from '../api/render'
import { cancelJob as cancelDownloadJob } from '../api/platformDownloader'
import type { HistoryItem } from '../types/api'

const MAX_VISIBLE = 3

// Mirror of App.tsx FULLSCREEN_PANELS — panels that hide the sidebar so the
// dock must extend all the way to the left edge.
const FULLSCREEN_PANELS = ['clip-studio']

export function ActiveJobsDock() {
  const { items, refresh } = useActiveJobs()
  const { t } = useI18n()
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const activePanel = useUIStore((s) => s.activePanel)
  const isFullscreen = FULLSCREEN_PANELS.includes(activePanel)

  const activeItems = items.filter(
    (j) => j.status === 'running' || j.status === 'queued',
  )

  if (activeItems.length === 0) return null

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

  return (
    <div
      style={{
        ...styles.dock,
        left: isFullscreen ? 0 : 'var(--sidebar-width, 0px)',
      }}
      role="region"
      aria-label="Active jobs"
    >
      <div style={styles.inner}>
        {visible.map((job) => (
          <DockRow key={job.job_id} job={job} onOpen={handleOpen} onCancel={handleCancel} />
        ))}
        {overflow > 0 && (
          <button
            style={styles.overflow}
            onClick={() => setActivePanel('home')}
            title={t('dock_open_all')}
          >
            +{overflow} {t('dock_running_suffix')}
          </button>
        )}
      </div>
    </div>
  )
}

function DockRow({
  job,
  onOpen,
  onCancel,
}: {
  job: HistoryItem
  onOpen: (job: HistoryItem) => void
  onCancel: (job: HistoryItem) => void
}) {
  const { t } = useI18n()
  const [hovered, setHovered] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  const pct = Math.max(0, Math.min(100, job.progress_percent || 0))
  const isQueued = job.status === 'queued'
  const kindLabel = job.kind === 'render' ? 'RENDER' : 'DOWNLOAD'
  const kindBg = job.kind === 'render' ? 'var(--accent-subtle)' : 'rgba(34, 197, 94, 0.12)'
  const kindFg = job.kind === 'render' ? 'var(--accent-primary)' : 'rgb(34, 197, 94)'
  const title = job.title || job.source_hint || job.job_id.slice(0, 8)
  const subtitle = isQueued
    ? t('dock_queued')
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
        {cancelling ? '…' : '×'}
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
}
