/**
 * QueueScreen — first-class Queue panel (WP2).
 *
 * Supersedes the old right-side QueueDrawer overlay: same data (shared
 * jobsStore poll) and the same reorder/hold/resume/cancel controls (existing
 * /api/jobs/queue/* endpoints), but as a full nav destination built on the
 * shared JobRow. The dock's "manage" button now navigates here.
 */
import React from 'react'
import { useActiveJobs, useJobsStore } from '@/stores/jobsStore'
import { useUIStore } from '@/stores/uiStore'
import { useI18n } from '@/i18n/useI18n'
import { moveJobToTop, moveJobToBottom, moveJob, holdJob, resumeJob } from '@/api/jobs'
import { cancelRender } from '@/api/render'
import { cancelJob as cancelDownloadJob } from '@/api/platformDownloader'
import {
  IconPlay, IconPause, IconToTop, IconToBottom, IconChevronUp, IconChevronDown, IconX,
} from '@/components/icons'
import { JobRow } from '@/components/JobRow'
import type { HistoryItem } from '@/types/api'

export function QueueScreen() {
  const { items, refresh } = useActiveJobs()
  const queueOrder = useJobsStore((s) => s.queueOrder)
  const heldIds = useJobsStore((s) => s.heldIds)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const { t } = useI18n()

  const activeItems = items.filter((j) => j.status === 'running' || j.status === 'queued')

  async function act(fn: () => Promise<unknown>) {
    try { await fn() } catch { /* 404 = state changed between poll+click; next poll reconciles */ }
    void refresh()
  }

  function openMonitor(job: HistoryItem) {
    if (job.kind !== 'render') return
    setMonitorJobId(job.job_id)
    setActivePanel('clip-studio')
  }

  return (
    <div style={styles.screen}>
      <header style={styles.header}>
        <span style={styles.title}>{t('queue_title')}</span>
        <span style={styles.count}>{activeItems.length}</span>
      </header>

      <div style={styles.body}>
        {activeItems.length === 0 ? (
          <div style={styles.empty}>{t('queue_empty')}</div>
        ) : (
          activeItems.map((job) => (
            <QueueEntry
              key={job.job_id}
              job={job}
              queueOrder={queueOrder}
              heldIds={heldIds}
              act={act}
              onOpen={openMonitor}
            />
          ))
        )}
      </div>
    </div>
  )
}

function QueueEntry({ job, queueOrder, heldIds, act, onOpen }: {
  job: HistoryItem
  queueOrder: string[]
  heldIds: string[]
  act: (fn: () => Promise<unknown>) => void
  onOpen: (job: HistoryItem) => void
}) {
  const { t } = useI18n()
  const isQueued = job.status === 'queued'
  const isRenderQueued = isQueued && job.kind === 'render'
  const isHeld = isRenderQueued && heldIds.includes(job.job_id)
  const title = job.title || job.source_hint || job.job_id.slice(0, 8)

  const posIdx = isHeld ? -1 : isQueued ? queueOrder.indexOf(job.job_id) : -1
  const total = queueOrder.length
  const canUp = posIdx > 0
  const canDown = posIdx >= 0 && posIdx < total - 1

  const subtitle = isHeld
    ? t('queue_paused')
    : isQueued
      ? (posIdx >= 0 ? `#${posIdx + 1}/${total}` : job.stage || '')
      : job.message || job.stage || t('queue_running')

  const cancelFn = () => (job.kind === 'render' ? cancelRender(job.job_id) : cancelDownloadJob(job.job_id))

  const actions = (
    <>
      {isHeld ? (
        <button style={styles.ctl} title={t('queue_resume')} aria-label={t('queue_resume')} onClick={() => act(() => resumeJob(job.job_id))}><IconPlay size={12} /></button>
      ) : (
        <>
          {canUp && <button style={styles.ctl} title={t('dock_move_top')} onClick={() => act(() => moveJobToTop(job.job_id))}><IconToTop size={12} /></button>}
          {canUp && <button style={styles.ctl} title={t('queue_move_up')} onClick={() => act(() => moveJob(job.job_id, -1))}><IconChevronUp size={12} /></button>}
          {canDown && <button style={styles.ctl} title={t('queue_move_down')} onClick={() => act(() => moveJob(job.job_id, 1))}><IconChevronDown size={12} /></button>}
          {canDown && <button style={styles.ctl} title={t('dock_move_bottom')} onClick={() => act(() => moveJobToBottom(job.job_id))}><IconToBottom size={12} /></button>}
          {isRenderQueued && <button style={styles.ctl} title={t('queue_pause')} aria-label={t('queue_pause')} onClick={() => act(() => holdJob(job.job_id))}><IconPause size={12} /></button>}
        </>
      )}
      <span style={{ flex: 1 }} />
      <button style={{ ...styles.ctl, color: 'var(--text-tertiary)' }} title={t('queue_cancel')} aria-label={t('queue_cancel')} onClick={() => act(cancelFn)}><IconX size={12} /></button>
    </>
  )

  return (
    <JobRow
      kind={job.kind}
      title={title}
      subtitle={subtitle}
      subtitleTone={isHeld ? 'warn' : 'default'}
      progressPct={job.progress_percent || 0}
      onOpen={job.kind === 'render' ? () => onOpen(job) : undefined}
      openTitle={t('queue_open')}
      actions={actions}
    />
  )
}

const styles: Record<string, React.CSSProperties> = {
  screen: { height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 },
  header: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle)', flexShrink: 0,
  },
  title: { fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '.02em' },
  count: {
    fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 999,
    background: 'var(--border-subtle)', color: 'var(--text-secondary)',
  },
  body: {
    flex: 1, minHeight: 0, overflowY: 'auto', padding: '12px 16px',
    display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 760,
  },
  empty: { padding: '48px 16px', textAlign: 'center', fontSize: 12, color: 'var(--text-tertiary)' },
  ctl: {
    width: 26, height: 24, border: '1px solid var(--border-subtle)', borderRadius: 6,
    background: 'transparent', color: 'var(--accent-primary)', cursor: 'pointer',
    fontSize: 12, lineHeight: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  },
}
