import { useState } from 'react'
import { AIChip } from '../../../components/ui/AIChip'
import { ScoreBadge } from '../../../components/ui/ScoreBadge'
import { type ReviewCardData, type ReviewCardStatus } from '../types'

interface ReviewCardProps {
  data: ReviewCardData
  status: ReviewCardStatus
  isComparisonOpen: boolean
  onApprove: () => void
  onReject: () => void
  onRestore: () => void
  onCompare: () => void
}

export function ReviewCard({
  data,
  status,
  isComparisonOpen,
  onApprove,
  onReject,
  onRestore,
  onCompare,
}: ReviewCardProps) {
  const [approveHovered, setApproveHovered] = useState(false)
  const [compareHovered, setCompareHovered] = useState(false)
  const [rejectHovered, setRejectHovered] = useState(false)
  const [restoreHovered, setRestoreHovered] = useState(false)

  const isApproved = status === 'approved'
  const isRejected = status === 'rejected'

  const cardStyle = {
    backgroundColor: isApproved ? 'var(--status-success-bg)' : 'var(--surface-card)',
    border: `1px solid ${isApproved ? 'var(--status-success)' : 'var(--border-subtle)'}`,
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-4)',
    display: 'flex' as const,
    flexDirection: 'column' as const,
    gap: 'var(--space-3)',
    opacity: isRejected ? 0.45 : 1,
    transition: 'background-color var(--duration-fast) var(--ease-out), border-color var(--duration-fast) var(--ease-out), opacity var(--duration-fast) var(--ease-out)',
  }

  return (
    <div style={cardStyle}>
      {/* Row 1: title left, score+chip right */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
        <span
          style={{
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-primary)',
            flex: 1,
            minWidth: 0,
          }}
        >
          {data.title}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexShrink: 0 }}>
          <ScoreBadge value={data.confidence} size="sm" />
          <AIChip variant="applied" label="AI Director" />
        </div>
      </div>

      {/* Row 2: preview tag + clip label */}
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 'var(--space-1)' }}>
        {[data.previewTag, data.clipLabel].map((tag) => (
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

      {/* Row 3: reasoning */}
      <span
        style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--text-secondary)',
          lineHeight: 'var(--leading-normal)',
        }}
      >
        {data.reasoning}
      </span>

      {/* Row 4: impact */}
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--status-success)' }}>
        {data.impact}
      </span>

      {/* Row 5: action buttons */}
      {isRejected ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', flex: 1 }}>
            Skipped
          </span>
          <button
            onClick={onRestore}
            onMouseEnter={() => setRestoreHovered(true)}
            onMouseLeave={() => setRestoreHovered(false)}
            style={{
              height: '28px',
              padding: '0 var(--space-3)',
              border: `1px solid ${restoreHovered ? 'var(--border-strong)' : 'var(--border-default)'}`,
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontSize: 'var(--text-sm)',
              cursor: 'pointer',
              transition: 'border-color var(--duration-instant) var(--ease-out)',
            }}
          >
            Restore
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {/* Approve */}
          <button
            onClick={onApprove}
            onMouseEnter={() => setApproveHovered(true)}
            onMouseLeave={() => setApproveHovered(false)}
            style={{
              flex: 1,
              height: '28px',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              backgroundColor: isApproved
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
            {isApproved ? '✓ Approved' : 'Approve'}
          </button>

          {/* Compare */}
          <button
            onClick={onCompare}
            onMouseEnter={() => setCompareHovered(true)}
            onMouseLeave={() => setCompareHovered(false)}
            style={{
              height: '28px',
              padding: '0 var(--space-3)',
              border: `1px solid ${isComparisonOpen || compareHovered ? 'var(--accent-primary)' : 'var(--border-default)'}`,
              borderRadius: 'var(--radius-md)',
              backgroundColor: isComparisonOpen ? 'var(--accent-subtle)' : 'transparent',
              color: isComparisonOpen ? 'var(--accent-primary)' : 'var(--text-secondary)',
              fontSize: 'var(--text-sm)',
              cursor: 'pointer',
              transition: 'border-color var(--duration-instant) var(--ease-out), background-color var(--duration-instant) var(--ease-out)',
            }}
          >
            Compare
          </button>

          {/* Reject */}
          <button
            onClick={isApproved ? undefined : onReject}
            onMouseEnter={() => !isApproved && setRejectHovered(true)}
            onMouseLeave={() => setRejectHovered(false)}
            style={{
              height: '28px',
              padding: '0 var(--space-3)',
              border: `1px solid ${rejectHovered && !isApproved ? 'var(--status-error)' : 'transparent'}`,
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'transparent',
              color: isApproved ? 'var(--text-disabled)' : rejectHovered ? 'var(--status-error)' : 'var(--text-tertiary)',
              fontSize: 'var(--text-sm)',
              cursor: isApproved ? 'not-allowed' : 'pointer',
              opacity: isApproved ? 0.4 : 1,
              transition: 'color var(--duration-instant) var(--ease-out), border-color var(--duration-instant) var(--ease-out)',
              pointerEvents: isApproved ? 'none' : 'auto',
            }}
          >
            Reject
          </button>
        </div>
      )}
    </div>
  )
}
