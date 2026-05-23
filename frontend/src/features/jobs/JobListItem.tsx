/**
 * JobListItem — card for a single HistoryItem in the job list.
 */
import { ProgressBar } from '../../components/ui/ProgressBar'
import { JobStatusBadge } from './JobStatusBadge'
import { JobActionsMenu } from './JobActionsMenu'
import { formatRelativeTime, isActiveStatus } from './jobs.utils'
import type { HistoryItem } from '../../types/api'

export interface JobListItemProps {
  item: HistoryItem
  isSelected: boolean
  actionLoading: Set<string>
  onSelect: (jobId: string) => void
  onCancel: (jobId: string) => void
  onRetry: (jobId: string) => void
  onRerun: (jobId: string) => void
  onDelete: (jobId: string) => void
}

export function JobListItem({
  item,
  isSelected,
  actionLoading,
  onSelect,
  onCancel,
  onRetry,
  onRerun,
  onDelete,
}: JobListItemProps) {
  const isActive = isActiveStatus(item.status)
  // Estimate progress percent from counts when active
  const progressPercent =
    item.total_count > 0
      ? Math.round((item.completed_count / item.total_count) * 100)
      : 0

  return (
    <div
      data-testid={`job-list-item-${item.job_id}`}
      style={{
        padding: 'var(--space-4)',
        borderBottom: '1px solid var(--color-border)',
        backgroundColor: isSelected
          ? 'var(--color-bg-elevated)'
          : 'transparent',
        cursor: 'pointer',
        transition: 'background-color var(--duration-fast)',
      }}
      onClick={() => onSelect(item.job_id)}
    >
      {/* Title row */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 'var(--space-2)',
          marginBottom: 'var(--space-1)',
        }}
      >
        <span
          style={{
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            color: 'var(--color-text-primary)',
            fontSize: 'var(--font-size-sm)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
        >
          {item.title}
        </span>
        <JobStatusBadge status={item.status} size="sm" />
      </div>

      {/* Source hint */}
      {item.source_hint && (
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            marginBottom: 'var(--space-2)',
          }}
        >
          {item.source_hint}
        </div>
      )}

      {/* Progress bar for active jobs */}
      {isActive && (
        <div style={{ marginBottom: 'var(--space-2)' }}>
          <ProgressBar value={progressPercent} />
        </div>
      )}

      {/* Summary */}
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          marginBottom: 'var(--space-1)',
        }}
      >
        {item.total_count > 0 && (
          <span>
            {item.completed_count}/{item.total_count} parts
            {item.failed_count > 0 && (
              <span style={{ color: 'var(--color-error)' }}>
                {' '}· {item.failed_count} failed
              </span>
            )}
            {' · '}
          </span>
        )}
        {item.summary_text}
      </div>

      {/* Timestamp */}
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          opacity: 0.7,
          marginBottom: 'var(--space-2)',
        }}
      >
        {formatRelativeTime(item.created_at)}
      </div>

      {/* Actions — stop propagation so clicking a button doesn't select the row */}
      <div onClick={(e) => e.stopPropagation()}>
        <JobActionsMenu
          item={item}
          actionLoading={actionLoading}
          onCancel={onCancel}
          onRetry={onRetry}
          onRerun={onRerun}
          onDelete={onDelete}
          onDetails={onSelect}
        />
      </div>
    </div>
  )
}
