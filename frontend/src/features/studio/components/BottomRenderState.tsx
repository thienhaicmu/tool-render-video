import { useState, useEffect } from 'react'
import { RenderJobCard } from './RenderJobCard'
import { type RenderJobData } from '../types'
import { getJobHistory } from '../../../api/jobs'
import type { HistoryItem } from '../../../types/api'

const ACTIVE_STATES: RenderJobData['state'][] = ['rendering', 'preparing', 'reviewing']

export function BottomRenderState() {
  const [collapsed, setCollapsed] = useState(true)
  const [toggleHovered, setToggleHovered] = useState(false)
  const [jobs, setJobs] = useState<RenderJobData[]>([])

  useEffect(() => {
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
      const title = raw.length > 40 ? raw.slice(0, 40) + '…' : raw
      return {
        jobId: item.job_id,
        title,
        state,
        stage: item.stage || undefined,
      }
    }

    async function fetchJobs() {
      try {
        const res = await getJobHistory(20, 0)
        setJobs(res.items.map(mapItem))
      } catch {
        // silent — retry on next interval
      }
    }

    fetchJobs()
    const id = window.setInterval(fetchJobs, 5000)
    return () => window.clearInterval(id)
  }, [])

  const activeCount = jobs.filter((j) => ACTIVE_STATES.includes(j.state)).length
  const hasActive = activeCount > 0

  return (
    <div
      style={{
        height: collapsed ? '44px' : 'var(--bottom-panel-height)',
        flexShrink: 0,
        backgroundColor: 'var(--surface-panel)',
        borderTop: '1px solid var(--border-default)',
        transition: 'height var(--duration-panel) var(--ease-in-out)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header row — always visible */}
      <div
        style={{
          height: '44px',
          display: 'flex',
          alignItems: 'center',
          padding: '0 var(--space-4)',
          gap: 'var(--space-2)',
          flexShrink: 0,
        }}
      >
        {/* Pulse dot */}
        <span
          className={hasActive ? 'status-dot--running' : undefined}
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: hasActive ? 'var(--accent-primary)' : 'var(--text-tertiary)',
            flexShrink: 0,
          }}
        />

        {/* Context label */}
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: hasActive ? 'var(--text-secondary)' : 'var(--text-tertiary)',
          }}
        >
          {hasActive
            ? `${activeCount} render${activeCount > 1 ? 's' : ''} active · AI assembling final clips`
            : 'No active renders'}
        </span>

        <div style={{ flex: 1 }} />

        <button
          onClick={() => setCollapsed((c) => !c)}
          onMouseEnter={() => setToggleHovered(true)}
          onMouseLeave={() => setToggleHovered(false)}
          style={{
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            fontSize: '12px',
            padding: 'var(--space-1) var(--space-2)',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: toggleHovered ? 'var(--surface-card)' : 'transparent',
            transition: 'background-color var(--duration-instant) var(--ease-out)',
          }}
          aria-label={collapsed ? 'Expand render queue' : 'Collapse render queue'}
        >
          {collapsed ? '▸' : '▾'}
        </button>
      </div>

      {/* Expanded body */}
      {!collapsed && (
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: 'var(--space-2) var(--space-4) var(--space-3)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
          }}
        >
          {jobs.map((job) => (
            <RenderJobCard key={job.jobId} {...job} />
          ))}
        </div>
      )}
    </div>
  )
}
