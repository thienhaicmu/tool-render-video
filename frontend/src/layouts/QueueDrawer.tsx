/**
 * QueueDrawer — Pha 3.3a — full queue-management overlay.
 *
 * The dock is a glanceable strip (max 3 rows, top/bottom reorder only). This
 * right-side drawer lists ALL running + queued jobs with the full reorder
 * control set (⤴ top · ▲ up · ▼ down · ⤓ bottom) plus cancel, using the
 * endpoints shipped in Pha 3 / 3.2. Read-only data comes from the shared
 * jobsStore poll; actions refresh() immediately so the new order shows
 * without waiting for the 4 s tick.
 *
 * Reorder controls apply to queued *render* jobs only — downloads run on a
 * separate engine and aren't in the scheduler's queueOrder.
 */
import React, { useEffect } from 'react'
import { useActiveJobs, useJobsStore } from '../stores/jobsStore'
import { useUIStore } from '../stores/uiStore'
import { useI18n } from '../i18n/useI18n'
import type { TranslationKey } from '../i18n/translations'
import { moveJobToTop, moveJobToBottom, moveJob, holdJob, resumeJob } from '../api/jobs'
import { cancelRender } from '../api/render'
import { cancelJob as cancelDownloadJob } from '../api/platformDownloader'
import type { HistoryItem } from '../types/api'

export function QueueDrawer() {
  const open = useUIStore((s) => s.queueDrawerOpen)
  const setOpen = useUIStore((s) => s.setQueueDrawerOpen)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)
  const { items, refresh } = useActiveJobs()
  const queueOrder = useJobsStore((s) => s.queueOrder)
  const heldIds = useJobsStore((s) => s.heldIds)
  const { t } = useI18n()

  // Esc closes the drawer.
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  if (!open) return null

  const activeItems = items.filter(
    (j) => j.status === 'running' || j.status === 'queued',
  )

  // Run an action then refresh; swallow 404s (job changed state between
  // poll + click — the next poll reconciles).
  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
    } catch {
      /* ignore */
    }
    void refresh()
  }

  // Pha 4 — open a render job's detailed Monitor (Step 3) and close the
  // drawer. Downloads have no monitor in RenderWorkflow → no-op.
  function openMonitor(job: HistoryItem) {
    if (job.kind !== 'render') return
    setMonitorJobId(job.job_id)
    setOpen(false)
  }

  return (
    <div style={styles.backdrop} role="dialog" aria-modal="true" aria-label={t('queue_title')} onClick={() => setOpen(false)}>
      <div style={styles.panel} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <span style={styles.title}>{t('queue_title')}</span>
          <span style={styles.count}>{activeItems.length}</span>
          <span style={{ flex: 1 }} />
          <button style={styles.closeBtn} onClick={() => setOpen(false)} title={t('queue_close')} aria-label={t('queue_close')}>
            ×
          </button>
        </div>

        <div style={styles.body}>
          {activeItems.length === 0 ? (
            <div style={styles.empty}>{t('queue_empty')}</div>
          ) : (
            activeItems.map((job) => (
              <QueueRow key={job.job_id} job={job} queueOrder={queueOrder} heldIds={heldIds} act={act} onOpen={openMonitor} t={t} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function QueueRow({
  job,
  queueOrder,
  heldIds,
  act,
  onOpen,
  t,
}: {
  job: HistoryItem
  queueOrder: string[]
  heldIds: string[]
  act: (fn: () => Promise<unknown>) => void
  onOpen: (job: HistoryItem) => void
  t: (key: TranslationKey) => string
}) {
  const canOpen = job.kind === 'render'
  const pct = Math.max(0, Math.min(100, job.progress_percent || 0))
  const isQueued = job.status === 'queued'
  const isRenderQueued = isQueued && job.kind === 'render'
  // Pha 3.3b — a paused job is queued-but-held: out of the dispatch order,
  // shown as "Paused" with a Resume control instead of reorder.
  const isHeld = isRenderQueued && heldIds.includes(job.job_id)
  const kindLabel = job.kind === 'render' ? 'RENDER' : 'DOWNLOAD'
  const kindBg = job.kind === 'render' ? 'var(--accent-subtle)' : 'rgba(34,197,94,.12)'
  const kindFg = job.kind === 'render' ? 'var(--accent-primary)' : 'rgb(34,197,94)'
  const title = job.title || job.source_hint || job.job_id.slice(0, 8)

  const posIdx = isHeld ? -1 : isQueued ? queueOrder.indexOf(job.job_id) : -1
  const total = queueOrder.length
  const canUp = posIdx > 0
  const canDown = posIdx >= 0 && posIdx < total - 1

  const subtitle = isHeld
    ? t('queue_paused')
    : isQueued
      ? posIdx >= 0
        ? `#${posIdx + 1}/${total}`
        : job.stage || ''
      : job.message || job.stage || t('queue_running')

  const cancelFn = () =>
    job.kind === 'render' ? cancelRender(job.job_id) : cancelDownloadJob(job.job_id)

  return (
    <div style={styles.row}>
      <div style={styles.rowTop}>
        <span style={{ ...styles.kindBadge, background: kindBg, color: kindFg }}>{kindLabel}</span>
        {canOpen ? (
          <button
            style={{ ...styles.rowTitle, ...styles.rowTitleBtn }}
            title={t('queue_open')}
            onClick={() => onOpen(job)}
          >
            {title}
          </button>
        ) : (
          <span style={styles.rowTitle}>{title}</span>
        )}
        <span style={{ ...styles.rowSub, ...(isHeld ? { color: 'var(--status-warning, #eab308)', fontWeight: 700 } : null) }}>{subtitle}</span>
      </div>

      <div style={styles.progressWrap}>
        <span style={{ ...styles.progressBar, width: `${pct}%` }} />
      </div>

      <div style={styles.controls}>
        {isHeld ? (
          <button style={styles.ctlBtn} title={t('queue_resume')} aria-label={t('queue_resume')} onClick={() => act(() => resumeJob(job.job_id))}>▶</button>
        ) : (
          <>
            {canUp && (
              <button style={styles.ctlBtn} title={t('dock_move_top')} onClick={() => act(() => moveJobToTop(job.job_id))}>⤴</button>
            )}
            {canUp && (
              <button style={styles.ctlBtn} title={t('queue_move_up')} onClick={() => act(() => moveJob(job.job_id, -1))}>▲</button>
            )}
            {canDown && (
              <button style={styles.ctlBtn} title={t('queue_move_down')} onClick={() => act(() => moveJob(job.job_id, 1))}>▼</button>
            )}
            {canDown && (
              <button style={styles.ctlBtn} title={t('dock_move_bottom')} onClick={() => act(() => moveJobToBottom(job.job_id))}>⤓</button>
            )}
            {isRenderQueued && (
              <button style={styles.ctlBtn} title={t('queue_pause')} aria-label={t('queue_pause')} onClick={() => act(() => holdJob(job.job_id))}>⏸</button>
            )}
          </>
        )}
        <span style={{ flex: 1 }} />
        <button style={{ ...styles.ctlBtn, color: 'var(--text-tertiary)' }} title={t('queue_cancel')} aria-label={t('queue_cancel')} onClick={() => act(cancelFn)}>×</button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1800,
    display: 'flex', justifyContent: 'flex-end',
  },
  panel: {
    width: 'min(420px, 92vw)', height: '100%',
    background: 'var(--surface-panel, #1d1f23)',
    borderLeft: '1px solid var(--border-subtle)',
    boxShadow: '-8px 0 24px rgba(0,0,0,0.4)',
    display: 'flex', flexDirection: 'column',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  title: { fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '.02em' },
  count: {
    fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 999,
    background: 'var(--border-subtle)', color: 'var(--text-secondary)',
  },
  closeBtn: {
    width: 28, height: 28, border: 'none', background: 'transparent',
    color: 'var(--text-tertiary)', fontSize: 18, cursor: 'pointer', borderRadius: 6,
  },
  body: { flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 },
  empty: { padding: '32px 16px', textAlign: 'center', fontSize: 12, color: 'var(--text-tertiary)' },
  row: {
    border: '1px solid var(--border-subtle)', borderRadius: 8, padding: '8px 10px',
    background: 'var(--surface-card)', display: 'flex', flexDirection: 'column', gap: 6,
  },
  rowTop: { display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 },
  kindBadge: {
    fontSize: 9, fontWeight: 700, letterSpacing: '.06em', padding: '2px 6px',
    borderRadius: 4, whiteSpace: 'nowrap', flexShrink: 0,
  },
  rowTitle: {
    fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  rowTitleBtn: {
    border: 'none', background: 'transparent', textAlign: 'left',
    cursor: 'pointer', padding: 0, minWidth: 0,
  },
  rowSub: { fontSize: 10, color: 'var(--text-tertiary)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', flexShrink: 0 },
  progressWrap: { position: 'relative', height: 4, background: 'var(--border-subtle)', borderRadius: 2, overflow: 'hidden' },
  progressBar: { position: 'absolute', inset: 0, background: 'var(--accent-primary)', transition: 'width 0.3s ease' },
  controls: { display: 'flex', alignItems: 'center', gap: 4 },
  ctlBtn: {
    width: 26, height: 24, border: '1px solid var(--border-subtle)', borderRadius: 6,
    background: 'transparent', color: 'var(--accent-primary)', cursor: 'pointer',
    fontSize: 12, lineHeight: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  },
}
