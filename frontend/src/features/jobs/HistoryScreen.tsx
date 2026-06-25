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

  // ── S3.3 batch selection state ────────────────────────────────────────────
  // Tracks the set of jobIds in multi-select mode. Empty Set = not in
  // batch mode (no action bar). lastShiftAnchor remembers the row the
  // user shift-selected from so subsequent shift-clicks select ranges.
  const [batchSelected, setBatchSelected] = useState<Set<string>>(new Set())
  const [batchBusy, setBatchBusy] = useState(false)
  const lastShiftAnchorRef = useRef<string | null>(null)

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

  // ── S3.3 batch selection helpers ───────────────────────────────────────
  // toggleBatch(jobId, shift): no shift = toggle single. Shift = select
  // range from last anchor through jobId. Operates over the filtered
  // items list so the user's mental model matches what they see.
  function toggleBatch(jobId: string, withShift: boolean) {
    setBatchSelected((prev) => {
      const next = new Set(prev)
      if (withShift && lastShiftAnchorRef.current && lastShiftAnchorRef.current !== jobId) {
        const ids = filteredItems.map((it) => it.job_id)
        const a = ids.indexOf(lastShiftAnchorRef.current)
        const b = ids.indexOf(jobId)
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a]
          for (let i = lo; i <= hi; i++) next.add(ids[i])
        }
      } else {
        if (next.has(jobId)) next.delete(jobId)
        else next.add(jobId)
        lastShiftAnchorRef.current = jobId
      }
      return next
    })
  }

  function clearBatch() {
    setBatchSelected(new Set())
    lastShiftAnchorRef.current = null
  }

  // ESC clears selection while in batch mode.
  useEffect(() => {
    if (batchSelected.size === 0) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') clearBatch()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [batchSelected.size])

  async function handleBatchDelete() {
    if (batchSelected.size === 0 || batchBusy) return
    const ids = Array.from(batchSelected)
    if (!window.confirm(`Xóa ${ids.length} job đã chọn? Thao tác không thể hoàn tác.`)) return
    setBatchBusy(true)
    let okCount = 0
    let failCount = 0
    for (const id of ids) {
      try {
        await deleteJob(id, true)
        okCount++
      } catch {
        failCount++
      }
    }
    addNotification({
      title: `Đã xóa ${okCount} / ${ids.length} job`,
      message: failCount > 0 ? `${failCount} job xóa thất bại` : undefined,
      type: failCount > 0 ? 'warning' : 'success',
    })
    clearBatch()
    setBatchBusy(false)
    await refreshJobs()
  }

  async function handleBatchRetry() {
    if (batchSelected.size === 0 || batchBusy) return
    const ids = Array.from(batchSelected)
    setBatchBusy(true)
    let okCount = 0
    let failCount = 0
    for (const id of ids) {
      try {
        await resumeRender(id)
        okCount++
      } catch {
        failCount++
      }
    }
    addNotification({
      title: `Đã re-run ${okCount} / ${ids.length} job`,
      message: failCount > 0 ? `${failCount} job thất bại` : undefined,
      type: failCount > 0 ? 'warning' : 'success',
    })
    clearBatch()
    setBatchBusy(false)
    await refreshJobs()
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

      {/* S3.3 — batch action bar (only when selection > 0) */}
      {batchSelected.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 14px',
          background: 'var(--accent-dim, rgba(123,97,255,.12))',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
          fontSize: 11,
        }}>
          <span style={{ fontWeight: 700, color: 'var(--accent)' }}>
            {batchSelected.size} đã chọn
          </span>
          <span style={{ flex: 1 }} />
          <button
            onClick={handleBatchRetry}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 700,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-1)', cursor: batchBusy ? 'not-allowed' : 'pointer',
              opacity: batchBusy ? .5 : 1,
            }}
          >
            {batchBusy ? '…' : 'Re-run'}
          </button>
          <button
            onClick={handleBatchDelete}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 700,
              border: '1px solid rgba(var(--fail-rgb),.4)',
              background: 'rgba(var(--fail-rgb),.08)',
              color: 'var(--fail)', cursor: batchBusy ? 'not-allowed' : 'pointer',
              opacity: batchBusy ? .5 : 1,
            }}
          >
            {batchBusy ? '…' : 'Xóa'}
          </button>
          <button
            onClick={clearBatch}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 600,
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            Bỏ chọn (Esc)
          </button>
        </div>
      )}

      {/* Toggle batch-mode hint when no selection yet — minimal nudge */}
      {batchSelected.size === 0 && filteredItems.length > 0 && (
        <div style={{
          padding: '4px 14px',
          fontSize: 9, color: 'var(--text-3)',
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span>Click vào row để xem chi tiết · Shift+click để batch-select</span>
          <button
            onClick={() => {
              if (filteredItems[0]) toggleBatch(filteredItems[0].job_id, false)
            }}
            style={{
              padding: '2px 8px', borderRadius: 5, fontSize: 9, fontWeight: 700,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            Bật batch-mode
          </button>
        </div>
      )}

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
            batchSelected={batchSelected.size > 0 ? batchSelected : undefined}
            onToggleBatch={toggleBatch}
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
