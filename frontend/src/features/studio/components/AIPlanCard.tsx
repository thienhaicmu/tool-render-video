import { useState } from 'react'
import { AIChip } from '../../../components/ui/AIChip'
import { ScoreBadge } from '../../../components/ui/ScoreBadge'

export interface AIPlanCardProps {
  title: string
  confidence: number
  reasoning: string
  impact: string
  tags: string[]
  selected?: boolean
  onApprove?: () => void
  onIgnore?: () => void
  status?: 'pending' | 'approved' | 'rejected'
}

export function AIPlanCard({
  title,
  confidence,
  reasoning,
  impact,
  tags,
  selected = false,
  onApprove,
  onIgnore,
  status,
}: AIPlanCardProps) {
  const [approveHovered, setApproveHovered] = useState(false)
  const [ignoreHovered, setIgnoreHovered] = useState(false)
  const [isHovered, setIsHovered] = useState(false)

  const resolvedSelected = status === 'approved' ? true : status === 'rejected' ? false : selected
  const isRejected = status === 'rejected'

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        backgroundColor: resolvedSelected
          ? 'var(--accent-subtle)'
          : isHovered && !isRejected
          ? 'var(--surface-card-hover)'
          : 'var(--surface-card)',
        border: `1px solid ${resolvedSelected ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
        opacity: isRejected ? 0.5 : 1,
        transition: 'background-color var(--duration-fast) var(--ease-out), border-color var(--duration-fast) var(--ease-out), opacity var(--duration-fast) var(--ease-out)',
      }}
    >
      {/* Header: AIChip + ScoreBadge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <AIChip variant="applied" label="AI Director" />
        <ScoreBadge value={confidence} size="sm" />
      </div>

      {/* Title + reasoning */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <span
          style={{
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-primary)',
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
            lineHeight: 'var(--leading-normal)',
          }}
        >
          {reasoning}
        </span>
      </div>

      {/* Impact */}
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--status-success)' }}>
        {impact}
      </span>

      {/* Tags */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
        {tags.map((tag) => (
          <span
            key={tag}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: '18px',
              padding: '0 var(--space-2)',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--surface-input)',
              color: 'var(--text-tertiary)',
              fontSize: 'var(--text-xs)',
            }}
          >
            {tag}
          </span>
        ))}
      </div>

      {/* Action row */}
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        <button
          onClick={onApprove}
          onMouseEnter={() => setApproveHovered(true)}
          onMouseLeave={() => setApproveHovered(false)}
          style={{
            flex: 1,
            height: '30px',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            backgroundColor: resolvedSelected
              ? 'var(--status-success)'
              : approveHovered
              ? 'var(--accent-hover)'
              : 'var(--accent-primary)',
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
            cursor: 'pointer',
            transition: 'background-color var(--duration-instant) var(--ease-out)',
          }}
        >
          {resolvedSelected ? '✓ Approved' : 'Approve'}
        </button>
        <button
          onClick={onIgnore}
          onMouseEnter={() => setIgnoreHovered(true)}
          onMouseLeave={() => setIgnoreHovered(false)}
          style={{
            height: '30px',
            padding: '0 var(--space-3)',
            border: `1px solid ${ignoreHovered ? 'var(--border-strong)' : 'var(--border-default)'}`,
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'transparent',
            color: 'var(--text-secondary)',
            fontSize: 'var(--text-sm)',
            cursor: 'pointer',
            transition: 'border-color var(--duration-instant) var(--ease-out)',
          }}
        >
          {isRejected ? 'Restore' : 'Ignore'}
        </button>
      </div>
    </div>
  )
}
