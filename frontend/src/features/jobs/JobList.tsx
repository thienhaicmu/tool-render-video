/**
 * JobList — renders the paginated filtered list of HistoryItem[].
 */
import { Button } from '../../components/ui/Button'
import { JobListItem } from './JobListItem'
import { JobLoadingState } from './JobLoadingState'
import { JobErrorState } from './JobErrorState'
import { JobEmptyState } from './JobEmptyState'
import type { HistoryItem } from '../../types/api'

export interface JobListProps {
  items: HistoryItem[]
  loading: boolean
  error: string | null
  hasFilters: boolean
  selectedJobId: string | null
  actionLoading: Set<string>
  hasMore: boolean
  offset: number
  onSelect: (jobId: string) => void
  onCancel: (jobId: string) => void
  onRetry: (jobId: string) => void
  onRerun: (jobId: string) => void
  onDelete: (jobId: string) => void
  onRetryFetch: () => void
  onPrevPage: () => void
  onNextPage: () => void
}

export function JobList({
  items,
  loading,
  error,
  hasFilters,
  selectedJobId,
  actionLoading,
  hasMore,
  offset,
  onSelect,
  onCancel,
  onRetry,
  onRerun,
  onDelete,
  onRetryFetch,
  onPrevPage,
  onNextPage,
}: JobListProps) {
  if (loading) return <JobLoadingState />
  if (error) return <JobErrorState error={error} onRetry={onRetryFetch} />
  if (items.length === 0 && !hasFilters) return <JobEmptyState />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {items.length === 0 && hasFilters ? (
          <div
            style={{
              padding: 'var(--space-8)',
              textAlign: 'center',
              color: 'var(--color-text-secondary)',
              fontSize: 'var(--font-size-sm)',
            }}
          >
            No jobs match the current filters.
          </div>
        ) : (
          items.map((item) => (
            <JobListItem
              key={item.job_id}
              item={item}
              isSelected={selectedJobId === item.job_id}
              actionLoading={actionLoading}
              onSelect={onSelect}
              onCancel={onCancel}
              onRetry={onRetry}
              onRerun={onRerun}
              onDelete={onDelete}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: 'var(--space-3) var(--space-4)',
          borderTop: '1px solid var(--color-border)',
          gap: 'var(--space-2)',
        }}
      >
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={onPrevPage}
          data-testid="pagination-prev"
        >
          Previous
        </Button>
        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
          }}
        >
          {offset + 1}–{offset + items.length}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={!hasMore}
          onClick={onNextPage}
          data-testid="pagination-next"
        >
          Next
        </Button>
      </div>
    </div>
  )
}
