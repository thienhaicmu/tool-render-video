import React from 'react'
import { JobListItem } from './JobListItem'
import { JobLoadingState } from './JobLoadingState'
import { JobErrorState } from './JobErrorState'
import { JobEmptyState } from './JobEmptyState'
import { dateGroup } from './jobs.utils'
import type { HistoryItem } from '@/types/api'

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
  onDuplicate?: (jobId: string) => void
  onRetryFetch: () => void
  onPrevPage: () => void
  onNextPage: () => void
}

export function JobList({
  items, loading, error, hasFilters, selectedJobId,
  actionLoading, hasMore, offset,
  onSelect, onCancel, onRetry, onRerun, onDelete, onDuplicate,
  onRetryFetch, onPrevPage, onNextPage,
}: JobListProps) {
  if (loading) return <JobLoadingState />
  if (error)   return <JobErrorState error={error} onRetry={onRetryFetch} />
  if (items.length === 0 && !hasFilters) return <JobEmptyState />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {items.length === 0 && hasFilters ? (
          <div style={{
            padding: '32px 16px', textAlign: 'center',
            color: 'var(--text-3)', fontSize: 11,
          }}>
            Không tìm thấy kết quả.
          </div>
        ) : (() => {
          const nodes: React.ReactNode[] = []
          let lastGroup = ''
          items.forEach(item => {
            const group = dateGroup(item.created_at)
            if (group !== lastGroup) {
              lastGroup = group
              nodes.push(
                <div key={`group-${group}`} style={{
                  padding: '5px 10px 3px',
                  fontSize: 8, fontWeight: 700, letterSpacing: '.08em',
                  textTransform: 'uppercase', color: 'var(--text-3)',
                  borderBottom: '1px solid var(--border)',
                  background: 'var(--bg-panel)',
                  position: 'sticky', top: 0, zIndex: 1,
                }}>
                  {group}
                </div>
              )
            }
            nodes.push(
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
                onDuplicate={onDuplicate}
              />
            )
          })
          return nodes
        })()}
      </div>

      {/* Pagination */}
      {(offset > 0 || hasMore) && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '6px 10px', borderTop: '1px solid var(--border)',
          background: 'var(--bg-panel)', flexShrink: 0,
        }}>
          <button
            disabled={offset === 0}
            onClick={onPrevPage}
            data-testid="pagination-prev"
            style={{
              fontSize: 10, padding: '3px 10px', borderRadius: 5,
              border: '1px solid var(--border)', background: 'var(--bg-hover)',
              color: offset === 0 ? 'var(--text-3)' : 'var(--text-2)',
              cursor: offset === 0 ? 'not-allowed' : 'pointer', fontWeight: 600,
            }}
          >← Trước</button>
          <span style={{ fontSize: 9, color: 'var(--text-3)' }}>
            {offset + 1}–{offset + items.length}
          </span>
          <button
            disabled={!hasMore}
            onClick={onNextPage}
            data-testid="pagination-next"
            style={{
              fontSize: 10, padding: '3px 10px', borderRadius: 5,
              border: '1px solid var(--border)', background: 'var(--bg-hover)',
              color: !hasMore ? 'var(--text-3)' : 'var(--text-2)',
              cursor: !hasMore ? 'not-allowed' : 'pointer', fontWeight: 600,
            }}
          >Sau →</button>
        </div>
      )}
    </div>
  )
}
