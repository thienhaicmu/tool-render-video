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
import { useI18n } from '@/i18n/useI18n'
import { useActiveJobs } from '@/stores/jobsStore'
import { ApiError } from '@/api/client'
import { confirmDialog } from '@/components/ui/ConfirmDialog'
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

  const { t, lang } = useI18n()
  const addNotification = useUIStore((s) => s.addNotification)
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const setDuplicateSeedJobId = useUIStore((s) => s.setDuplicateSeedJobId)

  // ── Fetch ─────────────────────────────────────────────────────────────────
  const fetchPage = useCallback(async (newOffset: number) => {
    setLoading(true)
    setFetchError(null)
    try {
      // P3.E — status filter applies server-side over the FULL history,
      // not just the fetched page (the old client-side filter made the
      // header counts lie about anything beyond the current 20 rows).
      const result = await getJobHistory(
        PAGE_SIZE, newOffset,
        statusFilter !== 'all' ? statusFilter : undefined,
      )
      setItems(result.items)
      setHasMore(result.has_more)
      setOffset(newOffset)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to load history'
      setFetchError(msg)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  // Initial fetch + refetch from page 0 whenever the status filter changes.
  useEffect(() => {
    fetchPage(0)
  }, [fetchPage])

  const refreshJobs = useCallback(() => fetchPage(offset), [fetchPage, offset])

  // Pha 5.5 — auto-refresh off the shared jobsStore poll instead of a second
  // dedicated 5 s interval. Subscribing arms the single shared poll; each tick
  // (its `items` reference changes) re-fetches the current page while any job
  // on it is still active. One timer for the whole app, not two.
  const { items: liveJobs } = useActiveJobs()
  useEffect(() => {
    if (items.some((i) => isActiveStatus(i.status))) fetchPage(offset)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveJobs])

  // ── Filtered items ────────────────────────────────────────────────────────
  // P3.E — status filtering moved server-side (fetchPage); only the text
  // search stays client-side over the fetched page.
  const filteredItems = useMemo(() => {
    let result = items
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
      title: t('history_dup_title'),
      message: t('history_dup_msg'),
      type: 'info',
    })
  }

  async function handleDelete(jobId: string) {
    const choice = await confirmDialog({
      title: t('history_delete_title'),
      message: t('history_delete_msg'),
      buttons: [
        { id: 'delete', label: t('history_delete_confirm'), variant: 'danger' },
        { id: 'cancel', label: t('history_cancel') },
      ],
    })
    if (choice !== 'delete') return
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
    const choice = await confirmDialog({
      title: lang === 'vi' ? `Xóa ${ids.length} job đã chọn?` : `Delete ${ids.length} selected jobs?`,
      message: t('history_delete_msg'),
      buttons: [
        { id: 'delete', label: lang === 'vi' ? `Xóa ${ids.length} job` : `Delete ${ids.length} jobs`, variant: 'danger' },
        { id: 'cancel', label: t('history_cancel') },
      ],
    })
    if (choice !== 'delete') return
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
      title: lang === 'vi' ? `Đã xóa ${okCount} / ${ids.length} job` : `Deleted ${okCount} / ${ids.length} jobs`,
      message: failCount > 0 ? (lang === 'vi' ? `${failCount} job xóa thất bại` : `${failCount} jobs failed to delete`) : undefined,
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
      title: lang === 'vi' ? `Đã re-run ${okCount} / ${ids.length} job` : `Re-ran ${okCount} / ${ids.length} jobs`,
      message: failCount > 0 ? (lang === 'vi' ? `${failCount} job thất bại` : `${failCount} jobs failed`) : undefined,
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
            {t('history_title')}
          </div>
          {items.length > 0 && (
            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 1 }}>
              {items.length} job · {completedCount} {t('history_done')}{failedCount > 0 ? ` · ${failedCount} ${t('history_failed')}` : ''}{activeCount > 0 ? ` · ${activeCount} ${t('history_running')}` : ''}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          {activeCount > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
              background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(123,97,255,.3)',
            }}>
              {activeCount} {t('history_running')}
            </span>
          )}
          <button
            onClick={refreshJobs}
            disabled={loading}
            data-testid="refresh-btn"
            style={{
              fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 6,
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
            {batchSelected.size} {t('history_selected')}
          </span>
          <span style={{ flex: 1 }} />
          <button
            onClick={handleBatchRetry}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-1)', cursor: batchBusy ? 'not-allowed' : 'pointer',
              opacity: batchBusy ? .5 : 1,
            }}
          >
            {batchBusy ? '…' : t('history_rerun')}
          </button>
          <button
            onClick={handleBatchDelete}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
              border: '1px solid rgba(var(--fail-rgb),.4)',
              background: 'rgba(var(--fail-rgb),.08)',
              color: 'var(--fail)', cursor: batchBusy ? 'not-allowed' : 'pointer',
              opacity: batchBusy ? .5 : 1,
            }}
          >
            {batchBusy ? '…' : t('history_delete')}
          </button>
          <button
            onClick={clearBatch}
            disabled={batchBusy}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            {t('history_deselect')}
          </button>
        </div>
      )}

      {/* Toggle batch-mode hint when no selection yet — minimal nudge */}
      {batchSelected.size === 0 && filteredItems.length > 0 && (
        <div style={{
          padding: '4px 14px',
          fontSize: 10, color: 'var(--text-3)',
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span>{t('history_hint')}</span>
          <button
            onClick={() => {
              if (filteredItems[0]) toggleBatch(filteredItems[0].job_id, false)
            }}
            style={{
              padding: '2px 8px', borderRadius: 5, fontSize: 10, fontWeight: 700,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            {t('history_batch_on')}
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
