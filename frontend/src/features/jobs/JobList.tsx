import React, { useState } from 'react'
import { JobListItem } from './JobListItem'
import { useI18n } from '@/i18n/useI18n'
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
  /** S3.3 — batch selection. Pass a Set + toggle to enable; pass
   *  undefined to keep the standard single-select behaviour. */
  batchSelected?: Set<string>
  onToggleBatch?: (jobId: string, withShift: boolean) => void
  onRetryFetch: () => void
  onPrevPage: () => void
  onNextPage: () => void
}

export function JobList({
  items, loading, error, hasFilters, selectedJobId,
  actionLoading, hasMore, offset,
  onSelect, onCancel, onRetry, onRerun, onDelete, onDuplicate,
  batchSelected, onToggleBatch,
  onRetryFetch, onPrevPage, onNextPage,
}: JobListProps) {
  const { t } = useI18n()
  // P3.C - "session v1": older runs of the same source collapse under the
  // newest run. Key = source_hint (falls back to title / job_id so unknown
  // sources never merge incorrectly across different videos).
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const groupKeyOf = (it: HistoryItem) => it.source_hint || it.title || it.job_id
  const groupCounts = new Map<string, number>()
  for (const it of items) {
    const k = groupKeyOf(it)
    groupCounts.set(k, (groupCounts.get(k) ?? 0) + 1)
  }
  const seenGroups = new Set<string>()

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
            {t('history_no_results')}
          </div>
        ) : (() => {
          const nodes: React.ReactNode[] = []
          let lastGroup = ''
          items.forEach(item => {
            const srcKey = groupKeyOf(item)
            const runCount = groupCounts.get(srcKey) ?? 1
            const isFirstOfGroup = !seenGroups.has(srcKey)
            if (isFirstOfGroup) seenGroups.add(srcKey)
            const groupExpanded = expandedGroups.has(srcKey)
            // Older run of a collapsed multi-run group -> hidden.
            if (!isFirstOfGroup && runCount > 1 && !groupExpanded) return
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
                isBatchSelected={batchSelected ? batchSelected.has(item.job_id) : undefined}
                onToggleBatch={onToggleBatch}
              />
            )
            if (isFirstOfGroup && runCount > 1) {
              nodes.push(
                <button
                  key={`runs-${srcKey}`}
                  onClick={() => setExpandedGroups(prev => {
                    const next = new Set(prev)
                    if (next.has(srcKey)) next.delete(srcKey)
                    else next.add(srcKey)
                    return next
                  })}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '4px 10px 4px 24px',
                    fontSize: 10, fontWeight: 600,
                    color: 'var(--accent)', background: 'var(--bg-panel)',
                    border: 'none', borderBottom: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
                >
                  {groupExpanded
                    ? `▾ ${t('history_runs_collapse')}`
                    : `▸ ${runCount - 1} ${t('history_runs_more')}`}
                </button>
              )
            }
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
          >{t('history_prev')}</button>
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
          >{t('history_next')}</button>
        </div>
      )}
    </div>
  )
}
