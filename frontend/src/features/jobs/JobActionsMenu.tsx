/**
 * JobActionsMenu — action buttons for a job card.
 * Handles Cancel / Retry / Re-run / Details / Delete.
 */
import { Button } from '../../components/ui/Button'
import type { HistoryItem } from '../../types/api'
import { canCancel, canRetry, canRerun, canDelete } from './jobs.utils'

export interface JobActionsMenuProps {
  item: HistoryItem
  actionLoading: Set<string>
  onCancel: (jobId: string) => void
  onRetry: (jobId: string) => void
  onRerun: (jobId: string) => void
  onDelete: (jobId: string) => void
  onDetails: (jobId: string) => void
}

export function JobActionsMenu({
  item,
  actionLoading,
  onCancel,
  onRetry,
  onRerun,
  onDelete,
  onDetails,
}: JobActionsMenuProps) {
  const isLoading = actionLoading.has(item.job_id)

  return (
    <div
      style={{
        display: 'flex',
        gap: 'var(--space-2)',
        flexWrap: 'wrap',
        marginTop: 'var(--space-2)',
      }}
    >
      {canCancel(item) && (
        <Button
          variant="secondary"
          size="sm"
          loading={isLoading}
          onClick={() => onCancel(item.job_id)}
          data-testid={`cancel-btn-${item.job_id}`}
        >
          Cancel
        </Button>
      )}

      {canRetry(item) && (
        <Button
          variant="secondary"
          size="sm"
          loading={isLoading}
          onClick={() => onRetry(item.job_id)}
          data-testid={`retry-btn-${item.job_id}`}
        >
          Retry
        </Button>
      )}

      {canRerun(item) && (
        <Button
          variant="secondary"
          size="sm"
          loading={isLoading}
          onClick={() => onRerun(item.job_id)}
          data-testid={`rerun-btn-${item.job_id}`}
        >
          Re-run
        </Button>
      )}

      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDetails(item.job_id)}
        data-testid={`details-btn-${item.job_id}`}
      >
        Details
      </Button>

      {canDelete(item) && (
        <Button
          variant="danger"
          size="sm"
          loading={isLoading}
          onClick={() => onDelete(item.job_id)}
          data-testid={`delete-btn-${item.job_id}`}
        >
          Delete
        </Button>
      )}
    </div>
  )
}
