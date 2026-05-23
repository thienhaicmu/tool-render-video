/**
 * HistoryScreen — top-level history panel.
 * Manages fetch, pagination, filtering, and action handlers.
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import './HistoryScreen.css'

import { Button } from '../../components/ui/Button'
import { JobList } from './JobList'
import { JobFilters } from './JobFilters'
import { JobDetailDrawer } from './JobDetailDrawer'
import { isActiveStatus } from './jobs.utils'
import { getJobHistory } from '../../api/jobs'
import { cancelRender, retryRender, resumeRender } from '../../api/render'
import { deleteJob } from '../../api/jobs'
import { useUIStore } from '../../stores/uiStore'
import { ApiError } from '../../api/client'
import type { HistoryItem } from '../../types/api'
import type { StatusFilter } from './jobs.types'

const PAGE_SIZE = 20

export function HistoryScreen() {
  // ── Fetch state ───────────────────────────────────────────────────────────
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  // ── Filter state ──────────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // ── Detail drawer ─────────────────────────────────────────────────────────
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)

  // ── Action loading ────────────────────────────────────────────────────────
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set())

  const addNotification = useUIStore((s) => s.addNotification)

  // ── Fetch ─────────────────────────────────────────────────────────────────
  const fetchPage = useCallback(async (newOffset: number) => {
    setLoading(true)
    setFetchError(null)
    try {
      const result = await getJobHistory(PAGE_SIZE, newOffset)
      setItems(result.items)
      setHasMore(result.has_more)
      setOffset(newOffset)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to load history'
      setFetchError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchPage(0)
  }, [fetchPage])

  const refreshJobs = useCallback(() => fetchPage(offset), [fetchPage, offset])

  // ── Filtered items ────────────────────────────────────────────────────────
  const filteredItems = useMemo(() => {
    let result = items
    if (statusFilter !== 'all') {
      result = result.filter((item) => {
        if (statusFilter === 'running')   return isActiveStatus(item.status)
        if (statusFilter === 'completed') return item.status === 'completed' || item.status === 'partial'
        if (statusFilter === 'failed')    return item.status === 'failed'
        if (statusFilter === 'cancelled') return item.status === 'cancelled' || item.status === 'interrupted'
        return true
      })
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (item) =>
          item.job_id.toLowerCase().includes(q) ||
          item.title.toLowerCase().includes(q) ||
          (item.source_hint ?? '').toLowerCase().includes(q),
      )
    }
    return result
  }, [items, statusFilter, search])

  const hasFilters = search.trim().length > 0 || statusFilter !== 'all'

  // ── Action helpers ────────────────────────────────────────────────────────
  function addToLoading(jobId: string) {
    setActionLoading((prev) => new Set(prev).add(jobId))
  }
  function removeFromLoading(jobId: string) {
    setActionLoading((prev) => {
      const s = new Set(prev)
      s.delete(jobId)
      return s
    })
  }

  async function handleCancel(jobId: string) {
    addToLoading(jobId)
    try {
      await cancelRender(jobId)
      addNotification({ title: 'Job canceled', type: 'success' })
      await refreshJobs()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Cancel failed'
      addNotification({ title: msg, type: 'error' })
    } finally {
      removeFromLoading(jobId)
    }
  }

  async function handleRetry(jobId: string) {
    addToLoading(jobId)
    try {
      await retryRender(jobId)
      addNotification({ title: 'Retry started', type: 'success' })
      await refreshJobs()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Retry failed'
      addNotification({ title: msg, type: 'error' })
    } finally {
      removeFromLoading(jobId)
    }
  }

  async function handleRerun(jobId: string) {
    addToLoading(jobId)
    try {
      await resumeRender(jobId)
      addNotification({ title: 'Re-run started', type: 'success' })
      await refreshJobs()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Re-run failed'
      addNotification({ title: msg, type: 'error' })
    } finally {
      removeFromLoading(jobId)
    }
  }

  async function handleDelete(jobId: string) {
    if (!window.confirm('Delete this job and its files?')) return
    addToLoading(jobId)
    try {
      await deleteJob(jobId, true)
      addNotification({ title: 'Job deleted', type: 'success' })
      if (selectedJobId === jobId) setSelectedJobId(null)
      await refreshJobs()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Delete failed'
      addNotification({ title: msg, type: 'error' })
    } finally {
      removeFromLoading(jobId)
    }
  }

  function handleSelect(jobId: string) {
    setSelectedJobId((prev) => (prev === jobId ? null : jobId))
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="history-screen">
      {/* Header */}
      <div className="history-header">
        <h1>Render History</h1>
        <Button
          variant="secondary"
          size="sm"
          onClick={refreshJobs}
          disabled={loading}
          data-testid="refresh-btn"
        >
          {loading ? 'Loading…' : 'Refresh'}
        </Button>
      </div>

      {/* Filters */}
      <JobFilters
        search={search}
        onSearchChange={setSearch}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
      />

      {/* Main content area */}
      <div className="history-content">
        <div className="history-list-pane">
          <JobList
            items={filteredItems}
            loading={loading}
            error={fetchError}
            hasFilters={hasFilters}
            selectedJobId={selectedJobId}
            actionLoading={actionLoading}
            hasMore={hasMore}
            offset={offset}
            onSelect={handleSelect}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onRerun={handleRerun}
            onDelete={handleDelete}
            onRetryFetch={() => fetchPage(offset)}
            onPrevPage={() => fetchPage(Math.max(0, offset - PAGE_SIZE))}
            onNextPage={() => fetchPage(offset + PAGE_SIZE)}
          />
        </div>

        {selectedJobId && (
          <div className="history-detail-pane">
            <JobDetailDrawer
              jobId={selectedJobId}
              onClose={() => setSelectedJobId(null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
