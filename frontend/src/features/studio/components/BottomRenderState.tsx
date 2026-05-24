import { useState, useEffect } from 'react'
import { RenderJobCard } from './RenderJobCard'
import { type RenderJobData } from '../types'
import { getJobHistory } from '../../../api/jobs'
import { useI18n } from '../../../i18n/useI18n'
import type { HistoryItem } from '../../../types/api'

const ACTIVE_STATES: RenderJobData['state'][] = ['rendering', 'preparing', 'reviewing']

function mapItem(item: HistoryItem): RenderJobData {
  let state: RenderJobData['state']
  const s = item.status
  if (s === 'running') {
    state = 'rendering'
  } else if (s === 'interrupted' || s === 'cancelled' || s === 'cancelling') {
    state = 'failed'
  } else if (s === 'queued' || s === 'completed' || s === 'failed') {
    state = s as RenderJobData['state']
  } else {
    state = 'failed'
  }
  const raw = item.title || item.source_hint || item.job_id
  const title = raw.length > 44 ? raw.slice(0, 44) + '…' : raw
  return {
    jobId: item.job_id,
    title,
    state,
    stage: item.stage || undefined,
    createdAt: item.created_at,
    outputDir: item.output_dir,
    canOpenFolder: item.can_open_folder,
    completedCount: item.completed_count,
    failedCount: item.failed_count,
    totalCount: item.total_count,
    summaryText: item.summary_text,
    kind: item.kind,
  }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export { relativeTime }

export function BottomRenderState() {
  const { t } = useI18n()
  const [collapsed, setCollapsed] = useState(true)
  const [toggleHovered, setToggleHovered] = useState(false)
  const [jobs, setJobs] = useState<RenderJobData[]>([])

  useEffect(() => {
    async function fetchJobs() {
      try {
        const res = await getJobHistory(20, 0)
        setJobs(res.items.map(mapItem))
      } catch { /* silent */ }
    }
    fetchJobs()
    const id = window.setInterval(fetchJobs, 5000)
    return () => window.clearInterval(id)
  }, [])

  const activeCount = jobs.filter((j) => ACTIVE_STATES.includes(j.state)).length
  const hasActive = activeCount > 0

  const statusLabel = hasActive
    ? `${activeCount} ${activeCount > 1 ? t('history_active_plural') : t('history_active_single')} · ${t('history_ai_assembling')}`
    : t('history_no_active')

  return (
    <div style={{
      height: collapsed ? '44px' : 'var(--bottom-panel-height)',
      flexShrink: 0,
      backgroundColor: 'var(--surface-panel)',
      borderTop: '1px solid var(--border-default)',
      transition: 'height var(--duration-panel) var(--ease-in-out)',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header row */}
      <div style={styles.headerRow}>
        <span
          className={hasActive ? 'status-dot--running' : undefined}
          style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            backgroundColor: hasActive ? 'var(--accent-primary)' : 'var(--border-default)',
            flexShrink: 0,
          }}
        />
        <span style={{
          fontSize: 'var(--text-sm)',
          fontWeight: 'var(--weight-semibold)' as unknown as number,
          color: hasActive ? 'var(--text-secondary)' : 'var(--text-tertiary)',
        }}>
          {statusLabel}
        </span>
        {jobs.length > 0 && !hasActive && (
          <span style={styles.jobCount}>{jobs.length}</span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setCollapsed((c) => !c)}
          onMouseEnter={() => setToggleHovered(true)}
          onMouseLeave={() => setToggleHovered(false)}
          style={{
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            fontSize: '11px',
            padding: 'var(--space-1) var(--space-2)',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: toggleHovered ? 'var(--surface-card)' : 'transparent',
            transition: 'background-color var(--duration-instant) var(--ease-out)',
          }}
          aria-label={collapsed ? t('history_expand') : t('history_collapse')}
        >
          {collapsed ? '▸ History' : '▾ History'}
        </button>
      </div>

      {/* Expanded body */}
      {!collapsed && (
        <div style={styles.body}>
          {jobs.length === 0 ? (
            <div style={styles.emptyText}>No render history yet.</div>
          ) : (
            jobs.map((job) => <RenderJobCard key={job.jobId} {...job} />)
          )}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  headerRow: {
    height: '44px',
    display: 'flex',
    alignItems: 'center',
    padding: '0 var(--space-4)',
    gap: 'var(--space-2)',
    flexShrink: 0,
  },
  jobCount: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '10px',
    padding: '0 6px',
    lineHeight: '18px',
  },
  body: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-2) var(--space-3) var(--space-3)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  emptyText: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    padding: 'var(--space-2)',
    textAlign: 'center' as const,
  },
}
