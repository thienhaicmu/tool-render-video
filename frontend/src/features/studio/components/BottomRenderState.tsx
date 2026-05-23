import { useState } from 'react'
import { RenderJobCard } from './RenderJobCard'
import { type RenderJobData } from '../types'

const MOCK_JOBS: RenderJobData[] = [
  {
    jobId: 'mock-1',
    title: 'TikTok Highlight Reel',
    state: 'rendering',
    progress: 67,
    stage: 'Encoding vertical 9:16',
    eta: '~40s',
    platform: 'TikTok',
  },
  {
    jobId: 'mock-2',
    title: 'Instagram Story Cut',
    state: 'reviewing',
    platform: 'Instagram',
  },
  {
    jobId: 'mock-3',
    title: 'YouTube Long Version',
    state: 'queued',
    platform: 'YouTube',
  },
]

const ACTIVE_STATES: RenderJobData['state'][] = ['rendering', 'preparing', 'reviewing']

export function BottomRenderState() {
  const [collapsed, setCollapsed] = useState(true)
  const [toggleHovered, setToggleHovered] = useState(false)

  const activeCount = MOCK_JOBS.filter((j) => ACTIVE_STATES.includes(j.state)).length
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
            backgroundColor: hasActive ? 'var(--accent-primary)' : 'var(--text-disabled)',
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
          {MOCK_JOBS.map((job) => (
            <RenderJobCard key={job.jobId} {...job} />
          ))}
        </div>
      )}
    </div>
  )
}
