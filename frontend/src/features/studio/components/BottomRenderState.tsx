import { useState } from 'react'
import { EmptyState } from '../../../components/ui/EmptyState'

export function BottomRenderState() {
  const [collapsed, setCollapsed] = useState(true)

  return (
    <div
      style={{
        height: collapsed ? '44px' : '180px',
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
          gap: 'var(--space-3)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-secondary)',
          }}
        >
          Render Queue
        </span>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
          }}
        >
          (no active render)
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setCollapsed((c) => !c)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            fontSize: '12px',
            padding: 'var(--space-1) var(--space-2)',
            borderRadius: 'var(--radius-sm)',
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
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <EmptyState
            primary="No active render"
            secondary="Submit a render to begin monitoring"
          />
        </div>
      )}
    </div>
  )
}
