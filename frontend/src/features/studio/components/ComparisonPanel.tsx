import { useState } from 'react'
import { AIChip } from '../../../components/ui/AIChip'

interface ComparisonPanelProps {
  isOpen: boolean
  onClose: () => void
}

export function ComparisonPanel({ isOpen, onClose }: ComparisonPanelProps) {
  const [closeHovered, setCloseHovered] = useState(false)

  return (
    <div
      style={{
        overflow: 'hidden',
        maxHeight: isOpen ? '400px' : '0px',
        opacity: isOpen ? 1 : 0,
        transition: 'max-height var(--duration-panel) var(--ease-out), opacity var(--duration-panel) var(--ease-out)',
      }}
    >
      <div
        style={{
          backgroundColor: 'var(--surface-card)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4)',
          marginTop: 'var(--space-2)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              textTransform: 'uppercase' as const,
              letterSpacing: '0.05em',
            }}
          >
            Compare
          </span>
          <button
            onClick={onClose}
            onMouseEnter={() => setCloseHovered(true)}
            onMouseLeave={() => setCloseHovered(false)}
            style={{
              border: 'none',
              backgroundColor: 'transparent',
              color: closeHovered ? 'var(--text-primary)' : 'var(--text-tertiary)',
              fontSize: 'var(--text-md)',
              cursor: 'pointer',
              lineHeight: 1,
              padding: 'var(--space-1)',
              transition: 'color var(--duration-instant) var(--ease-out)',
            }}
            aria-label="Close comparison"
          >
            ×
          </button>
        </div>

        {/* Two-column shell */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 'var(--space-3)',
            marginTop: 'var(--space-3)',
          }}
        >
          {(['Before', 'After'] as const).map((label) => (
            <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                {label}
              </span>
              <div
                style={{
                  aspectRatio: '9 / 16',
                  backgroundColor: 'var(--surface-input)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-disabled)' }}>
                  {label}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* AI explanation */}
        <div
          style={{
            marginTop: 'var(--space-3)',
            padding: 'var(--space-3)',
            backgroundColor: 'var(--ai-subtle)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
          }}
        >
          <AIChip variant="advisory" label="AI Analysis" />
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 'var(--leading-normal)' }}>
            AI predicts stronger retention due to faster hook.
          </span>
        </div>
      </div>
    </div>
  )
}
