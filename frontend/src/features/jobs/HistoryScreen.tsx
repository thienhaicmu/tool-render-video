/**
 * HistoryScreen — top-level history panel.
 * Manages fetch, pagination, filtering, and action handlers.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import './HistoryScreen.css'

import { JobList } from './JobList'
import { JobFilters } from './JobFilters'
import { JobDetailDrawer } from './JobDetailDrawer'
import { isActiveStatus } from './jobs.utils'
import { getJobHistory } from '@/api/jobs'
import { cancelRender, retryRender, resumeRender } from '@/api/render'
import { deleteJob } from '@/api/jobs'
import { useUIStore } from '@/stores/uiStore'
import { ApiError } from '@/api/client'
import type { HistoryItem } from '@/types/api'
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
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const setDuplicateSeedJobId = useUIStore((s) => s.setDuplicateSeedJobId)

  // ── Auto-refresh when active jobs exist ───────────────────────────────────
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  // Auto-refresh every 5s while any job is active
  useEffect(() => {
    if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    const hasActive = items.some(i => isActiveStatus(i.status))
    if (hasActive) {
      autoRefreshRef.current = setInterval(() => fetchPage(offset), 5000)
    }
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current) }
  }, [items, offset, fetchPage])

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

  function handleDuplicate(jobId: string) {
    // S2.5 — RenderWorkflow picks up duplicateSeedJobId on its next mount
    // and hydrates Step 2 + source from the old job's payload_json.
    setDuplicateSeedJobId(jobId)
    setActivePanel('clip-studio')
    addNotification({
      title: 'Đã copy settings',
      message: 'Configure step đã pre-fill từ job cũ',
      type: 'info',
    })
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
  const activeCount    = items.filter(i => isActiveStatus(i.status)).length
  const completedCount = items.filter(i => i.status === 'completed' || i.status === 'partial').length
  const failedCount    = items.filter(i => i.status === 'failed').length

  return (
    <div className="history-screen">
      <style>{`@keyframes job-pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>

      {/* ── Header ── */}
      <div style={{
        padding: '11px 14px 10px', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontFamily: 'var(--fh)', fontSize: 13, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.6px' }}>
            LỊCH SỬ RENDER
          </div>
          {items.length > 0 && (
            <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 1 }}>
              {items.length} job · {completedCount} xong{failedCount > 0 ? ` · ${failedCount} lỗi` : ''}{activeCount > 0 ? ` · ${activeCount} chạy` : ''}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          {activeCount > 0 && (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
              background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(123,97,255,.3)',
            }}>
              {activeCount} chạy
            </span>
          )}
          <button
            onClick={refreshJobs}
            disabled={loading}
            data-testid="refresh-btn"
            style={{
              fontSize: 10, fontWeight: 700, padding: '4px 10px', borderRadius: 6,
              border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-2)',
              fontFamily: 'var(--fh)', letterSpacing: '.4px',
              cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? .5 : 1,
            }}
          >
            {loading ? '…' : '↺'}
          </button>
        </div>
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
            onDuplicate={handleDuplicate}
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
