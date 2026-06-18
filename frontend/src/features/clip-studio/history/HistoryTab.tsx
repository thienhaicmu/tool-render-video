import { useState, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import { cancelRender, resumeRender } from '@/api/render'
import { clearHistory } from '@/api/maintenance'
import { useActiveJobs, useJobsStore } from '@/stores/jobsStore'
import type { HistoryItem } from '@/types/api'
import './HistoryTab.css'

const FILTERS = ['All', 'Done', 'Failed', 'Running'] as const
type Filter = typeof FILTERS[number]

const S: Record<string, { color: string; bg: string; border: string; label: string; icon: string }> = {
  completed:             { color: 'var(--ok)', bg: 'rgba(var(--ok-rgb),.12)',   border: 'rgba(var(--ok-rgb),.25)',   label: 'Done',        icon: '✓' },
  completed_with_errors: { color: 'var(--warn)', bg: 'rgba(var(--warn-rgb),.12)',  border: 'rgba(var(--warn-rgb),.25)',  label: 'Partial',     icon: '⚠' },
  failed:                { color: 'var(--fail)', bg: 'rgba(var(--fail-rgb),.12)',  border: 'rgba(var(--fail-rgb),.25)',  label: 'Failed',      icon: '✕' },
  running:               { color: 'var(--accent)', bg: 'rgba(var(--accent-rgb),.12)',  border: 'rgba(var(--accent-rgb),.3)',   label: 'Running',     icon: '⟳' },
  queued:                { color: 'var(--text-2)', bg: 'rgba(var(--text-rgb),.10)', border: 'rgba(var(--text-rgb),.2)',  label: 'Queued',      icon: '○' },
  interrupted:           { color: 'var(--warn)', bg: 'rgba(var(--warn-rgb),.12)',  border: 'rgba(var(--warn-rgb),.25)',  label: 'Interrupted', icon: '!' },
  cancelled:             { color: 'var(--text-3)', bg: 'rgba(var(--text-rgb),.10)',   border: 'rgba(var(--text-rgb),.2)',    label: 'Cancelled',   icon: '—' },
  cancelling:            { color: 'var(--text-3)', bg: 'rgba(var(--text-rgb),.10)',   border: 'rgba(var(--text-rgb),.2)',    label: 'Cancelling',  icon: '…' },
}
const sm = (s: string) => S[s] ?? { color: 'var(--text-2)', bg: 'rgba(var(--text-rgb),.10)', border: 'rgba(var(--text-rgb),.2)', label: s.replace(/_/g, ' '), icon: '?' }

function fmtDate(raw: string) {
  const d = new Date(raw)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const yest = new Date(now); yest.setDate(yest.getDate() - 1)
  const isYesterday = d.toDateString() === yest.toDateString()
  if (isToday) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (isYesterday) return `Yesterday ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function groupByDate(jobs: HistoryItem[]) {
  const today: HistoryItem[] = [], yesterday: HistoryItem[] = [], older: HistoryItem[] = []
  const now = new Date()
  const yest = new Date(now); yest.setDate(yest.getDate() - 1)
  for (const j of jobs) {
    const d = new Date(j.created_at)
    if (d.toDateString() === now.toDateString()) today.push(j)
    else if (d.toDateString() === yest.toDateString()) yesterday.push(j)
    else older.push(j)
  }
  return { today, yesterday, older }
}

function ProgressRing({ done, total, color }: { done: number; total: number; color: string }) {
  if (total === 0) return null
  return (
    <span style={{ fontSize: 10, color, fontWeight: 700 }}>
      {done}/{total}
    </span>
  )
}

function JobRow({
  job, onOpen, onCancel, onMonitor,
}: {
  job: HistoryItem
  onOpen: (j: HistoryItem) => void
  onCancel: (j: HistoryItem) => void
  onMonitor: (j: HistoryItem) => void
}) {
  const st = sm(job.status)
  const isRunning = job.status === 'running'
  const isQueued = job.status === 'queued'
  // Bug #10 fix: use the job-level progress_percent (added 2026-06-15 to
  // /api/jobs/history). Falls back to parts-based ratio for older API
  // responses that pre-dated the field. Job-level progress works for
  // every stage (transcribing, scene_detection, etc.) — the parts ratio
  // only works after segment_building.
  const pct = isRunning
    ? Math.max(
        0,
        Math.min(
          100,
          job.progress_percent ||
            (job.total_count > 0
              ? Math.round((job.completed_count / job.total_count) * 100)
              : 0),
        ),
      )
    : 0
  // Bug #11 fix: derive a coarse ETA from elapsed time + progress %. Only
  // useful once progress is > 3% (numeric noise floor) and < 99%.
  const etaSec = (() => {
    if (!isRunning || pct < 3 || pct >= 99) return 0
    const startedAt = Date.parse(job.created_at)
    if (!Number.isFinite(startedAt)) return 0
    const elapsedSec = (Date.now() - startedAt) / 1000
    if (elapsedSec < 5) return 0
    return Math.max(0, Math.round((elapsedSec * (100 - pct)) / pct))
  })()
  const etaLabel = etaSec > 0
    ? etaSec >= 60
      ? `~${Math.round(etaSec / 60)}m left`
      : `~${etaSec}s left`
    : ''

  // Bug #3 fix: a running job's row should jump straight to the Rendering
  // screen (monitor view) on click; non-active rows open the detail drawer
  // as before.
  const handleRowClick = () => {
    if (isRunning || isQueued) onMonitor(job)
    else onOpen(job)
  }

  return (
    <div className={`hist-row${isRunning ? ' is-running' : ''}`} onClick={handleRowClick}>
      <div className={`hist-ico${isRunning ? ' spin' : ''}`} style={{ background: st.bg, borderColor: st.border, color: st.color }}>
        {st.icon}
      </div>
      <div className="hist-row-main">
        <div className="hist-row-title">{job.title || job.source_hint || `Render Job #${job.job_id.slice(0, 8)}`}</div>
        <div className="hist-row-sub">
          <span className="mono">{job.job_id.slice(0, 8)}</span>
          {job.completed_count > 0 && <span className="hist-tag ok">✓ {job.completed_count} clip{job.completed_count !== 1 ? 's' : ''}</span>}
          {job.failed_count > 0 && <span className="hist-tag fail">✕ {job.failed_count} failed</span>}
          {isRunning && job.total_count > 0 && <ProgressRing done={job.completed_count} total={job.total_count} color="var(--accent)" />}
        </div>
      </div>
      {isRunning && (
        <div className="hist-prog">
          <div className="hist-prog-track"><i style={{ width: `${pct}%` }} /></div>
          <div className="hist-prog-meta">
            <span className="pct">{pct}%</span>
            {etaLabel && <span className="eta">{etaLabel}</span>}
          </div>
        </div>
      )}
      <span className="hist-date">{fmtDate(job.created_at)}</span>
      <span className="hist-badge" style={{ background: st.bg, color: st.color, borderColor: st.border }}>{st.label.toUpperCase()}</span>
      {(isRunning || isQueued)
        ? <button className="hist-cancel" title="Cancel render" onClick={(e) => { e.stopPropagation(); onCancel(job) }}>✕ Cancel</button>
        : <span className="hist-chev">›</span>}
    </div>
  )
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="hist-sec">
      <span className="label">{label}</span>
      <span className="count">{count}</span>
    </div>
  )
}

function DetailDrawer({
  job, onClose, onCancel, onResume, onMonitor,
}: {
  job: HistoryItem
  onClose: () => void
  onCancel: (j: HistoryItem) => void
  onResume: (j: HistoryItem) => void
  onMonitor: (j: HistoryItem) => void
}) {
  const st = sm(job.status)
  const isActive = job.status === 'running' || job.status === 'queued'
  const isInterrupted = job.status === 'interrupted' || job.status === 'failed'
  return (
    <div style={{
      position: 'fixed' as const, inset: 0, zIndex: 999,
      display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
    }} onClick={onClose}>
      <div
        style={{
          width: 340, height: '100%',
          background: 'var(--surface-card)',
          borderLeft: '1px solid var(--border-default)',
          display: 'flex', flexDirection: 'column' as const,
          boxShadow: '-12px 0 48px var(--surface-overlay)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
              {job.title || job.source_hint || 'Render Job'}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2, fontFamily: 'monospace' }}>#{job.job_id}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}>×</button>
        </div>

        {/* Stats grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--border-default)', margin: 16, borderRadius: 10, overflow: 'hidden' }}>
          {[
            { label: 'Status', value: st.label, color: st.color },
            { label: 'Clips done', value: `${job.completed_count}`, color: 'var(--ok)' },
            { label: 'Failed', value: `${job.failed_count}`, color: job.failed_count > 0 ? 'var(--fail)' : 'var(--text-3)' },
            { label: 'Total', value: `${job.total_count}`, color: 'var(--text-1)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'var(--surface-card)', padding: '12px 14px' }}>
              <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Summary text */}
        {job.summary_text && (
          <div style={{ padding: '0 16px 16px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 6 }}>Summary</div>
            <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.6, background: 'var(--surface-panel)', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-default)' }}>
              {job.summary_text}
            </div>
          </div>
        )}

        {/* Output dir */}
        {job.output_dir && (
          <div style={{ padding: '0 16px 16px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 6 }}>Output folder</div>
            <div style={{
              fontSize: 10, color: 'var(--text-2)', fontFamily: 'monospace',
              background: 'var(--surface-panel)', padding: '8px 10px', borderRadius: 6,
              border: '1px solid var(--border-default)', wordBreak: 'break-all' as const,
            }}>
              {job.output_dir}
            </div>
          </div>
        )}

        {/* Actions — Bug #4 fix: status-aware controls so running jobs can
            be cancelled / monitored and interrupted jobs can be resumed
            directly from the drawer (previously only "Copy output path"
            was available, which was useless for active jobs). */}
        <div style={{ padding: '0 16px', marginTop: 'auto', paddingBottom: 20, display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
          {isActive && (
            <>
              <button
                onClick={() => { onMonitor(job); onClose() }}
                style={{
                  padding: '11px', borderRadius: 8, background: 'var(--brand-gradient-button)',
                  border: 'none', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  boxShadow: '0 1px 0 rgba(255,255,255,.25) inset, 0 2px 8px rgba(139,92,246,.30)',
                  letterSpacing: '-.005em',
                }}
              >
                ⟳ Open render monitor
              </button>
              <button
                onClick={() => { onCancel(job); onClose() }}
                style={{
                  padding: '10px', borderRadius: 8, background: 'transparent',
                  border: '1px solid var(--status-error)',
                  color: 'var(--status-error)',
                  fontSize: 12, fontWeight: 600, cursor: 'pointer',
                }}
              >
                ✕ Cancel render
              </button>
            </>
          )}
          {isInterrupted && (
            <button
              onClick={() => { onResume(job); onClose() }}
              style={{
                padding: '11px', borderRadius: 8, background: 'var(--brand-gradient-button)',
                border: 'none', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                boxShadow: '0 1px 0 rgba(255,255,255,.25) inset, 0 2px 8px rgba(139,92,246,.30)',
                letterSpacing: '-.005em',
              }}
            >
              ↻ Resume from last
            </button>
          )}
          {job.can_open_folder && job.output_dir && (
            <>
              {/* N1 (audit 2026-06-15): native folder open via Electron IPC.
                  Was previously only "Copy output path" — required user to
                  Win+E, paste, navigate manually. */}
              <button
                onClick={() => { window.electronAPI?.openPath?.(job.output_dir!) }}
                style={{
                  padding: '11px', borderRadius: 8, background: 'var(--surface-card-hover)',
                  border: '1px solid var(--border-strong)', color: 'var(--text-primary)',
                  fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
                </svg>
                Open folder
              </button>
              <button
                onClick={() => { navigator.clipboard.writeText(job.output_dir!).catch(() => {}) }}
                style={{
                  padding: '8px', borderRadius: 8, background: 'transparent',
                  border: '1px solid var(--border-default)', color: 'var(--text-tertiary)', fontSize: 11,
                  fontWeight: 500, cursor: 'pointer',
                }}
              >
                Copy path
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

interface HistoryTabProps {
  lang: Lang
  /** Switch the cs-shell active tab. Used to jump to the Render tab when
   *  user opens a running job from History so they can monitor / cancel. */
  onSwitchToRender?: () => void
}

export function HistoryTab({ lang: _lang, onSwitchToRender }: HistoryTabProps) {
  const [filter, setFilter]     = useState<Filter>('All')
  const [search, setSearch]     = useState('')
  const [selected, setSelected] = useState<HistoryItem | null>(null)
  const [clearing, setClearing] = useState(false)

  // Subscribe to the shared jobs store. The store owns the 4 s poll —
  // ActiveJobBadge + RenderWorkflow auto-reattach share the same fetch,
  // so we no longer triple-poll /api/jobs/history.
  const { items: jobs, loading, error, refresh } = useActiveJobs()

  // Cancel an active job from History row / drawer. Optimistic-only — the
  // shared poll loop will reflect the status flip to 'cancelling' →
  // 'cancelled' within at most 4 s; the explicit refresh() below shortens
  // that to ~one network round-trip.
  const handleCancel = useCallback(async (j: HistoryItem) => {
    try {
      await cancelRender(j.job_id)
      // Optimistic local update via the shared store so the row immediately
      // shows 'cancelling'.
      useJobsStore.setState((s) => ({
        items: s.items.map((x) => x.job_id === j.job_id ? { ...x, status: 'cancelling' } : x),
      }))
      refresh()
    } catch {
      // Ignore — next poll will surface the real status.
    }
  }, [refresh])

  // Resume an interrupted/failed job — backend creates a fresh job_id
  // continuing from the last successful part. Switch to Render tab so the
  // user can monitor the resumed run.
  const handleResume = useCallback(async (j: HistoryItem) => {
    try {
      await resumeRender(j.job_id)
      onSwitchToRender?.()
      refresh()
    } catch {
      // Surface as a banner — leave row in current state.
    }
  }, [onSwitchToRender, refresh])

  // Open the Render tab so RenderWorkflow's on-mount auto-reattach detects
  // this active job and lands on the Rendering monitor screen.
  const handleMonitor = useCallback((_j: HistoryItem) => {
    onSwitchToRender?.()
  }, [onSwitchToRender])

  // Clear all history. Active (running/queued) jobs are preserved server-side
  // (preserve_active default) so an in-flight render is never orphaned.
  const handleClearHistory = useCallback(async () => {
    if (clearing) return
    const running = jobs.filter((j) => j.status === 'running' || j.status === 'queued').length
    const msg = running > 0
      ? `Clear render history? ${running} active job(s) will be kept. This cannot be undone.`
      : 'Clear all render history? This cannot be undone.'
    if (!window.confirm(msg)) return
    setClearing(true)
    try {
      await clearHistory({ clearCache: false, preserveActive: true })
      await refresh()
    } catch {
      // leave history as-is; next poll reflects reality
    } finally {
      setClearing(false)
    }
  }, [clearing, jobs, refresh])

  const filtered = jobs.filter((j) => {
    if (filter === 'Done'    && !j.status.startsWith('completed')) return false
    if (filter === 'Failed'  && j.status !== 'failed')             return false
    if (filter === 'Running' && j.status !== 'running')            return false
    if (search) {
      const q = search.toLowerCase()
      if (!j.job_id.toLowerCase().includes(q) && !(j.title || j.source_hint || '').toLowerCase().includes(q)) return false
    }
    return true
  })

  const runningCount = jobs.filter((j) => j.status === 'running').length
  const doneCount    = jobs.filter((j) => j.status.startsWith('completed')).length
  const failedCount  = jobs.filter((j) => j.status === 'failed').length

  const { today, yesterday, older } = groupByDate(filtered)

  const _renderGroup = (label: string, items: HistoryItem[]) =>
    items.length > 0 && (
      <>
        <SectionHeader label={label} count={items.length} />
        <div className="hist-list">
          {items.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} onCancel={handleCancel} onMonitor={handleMonitor} />)}
        </div>
      </>
    )

  return (
    <div className="hist">
      {/* Toolbar */}
      <div className="hist-top">
        <div className="hist-top-inner">
          <div className="hist-head-row">
            <span className="hist-logo">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
              </svg>
            </span>
            <div className="hist-titles">
              <span className="hist-title">History</span>
              <span className="hist-subtitle">All your render jobs in one place</span>
            </div>
            <div className="hist-pills">
              {runningCount > 0 && <span className="hist-pill is-run">{runningCount} running</span>}
              {doneCount > 0 && <span className="hist-pill is-done">{doneCount} done</span>}
              {failedCount > 0 && <span className="hist-pill is-fail">{failedCount} failed</span>}
            </div>
            <div className="hist-actions">
              <button className="hist-icon-btn" onClick={() => { refresh() }} title="Refresh">↻</button>
              <button className="hist-clear" onClick={handleClearHistory} disabled={clearing || jobs.length === 0} title="Clear history (keeps active jobs)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                </svg>
                {clearing ? 'Clearing…' : 'Clear'}
              </button>
            </div>
          </div>

          <div className="hist-tools">
            <div className="hist-filters">
              {FILTERS.map((f) => (
                <button key={f} className={`hist-filter${filter === f ? ' is-sel' : ''}`} onClick={() => setFilter(f)}>{f}</button>
              ))}
            </div>
            <div className="hist-search">
              <span style={{ fontSize: 11, color: 'var(--text-3)' }}>🔍</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search…" />
            </div>
          </div>
        </div>
      </div>

      {/* Main */}
      <div className="hist-main">
        <div className="hist-main-inner">
          {loading && <div className="hist-state">Loading…</div>}
          {!loading && error && <div className="hist-state is-fail">⚠ {error}</div>}
          {!loading && !error && filtered.length === 0 && (
            <div className="hist-empty">
              <div className="hist-empty-icon" aria-hidden="true">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
                </svg>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                <div className="hist-empty-title">{search || filter !== 'All' ? 'No matches' : 'No render jobs yet'}</div>
                <div className="hist-empty-sub">
                  {search || filter !== 'All' ? 'Try clearing the filter or search.' : 'Your finished and in-progress renders will appear here.'}
                </div>
              </div>
            </div>
          )}
          {!loading && !error && filtered.length > 0 && (
            <>
              {_renderGroup('Today', today)}
              {_renderGroup('Yesterday', yesterday)}
              {_renderGroup('Older', older)}
            </>
          )}
        </div>
      </div>

      {/* Detail drawer */}
      {selected && (
        <DetailDrawer
          job={selected}
          onClose={() => setSelected(null)}
          onCancel={handleCancel}
          onResume={handleResume}
          onMonitor={handleMonitor}
        />
      )}
    </div>
  )
}
