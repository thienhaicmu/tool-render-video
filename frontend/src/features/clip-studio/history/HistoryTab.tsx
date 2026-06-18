import { useState, useCallback } from 'react'
import type { Lang } from '../ClipStudio'
import { cancelRender, resumeRender } from '@/api/render'
import { clearHistory } from '@/api/maintenance'
import { useActiveJobs, useJobsStore } from '@/stores/jobsStore'
import type { HistoryItem } from '@/types/api'

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
  const [hov, setHov] = useState(false)
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
    <div
      onClick={handleRowClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 20px',
        minHeight: 64,
        background: hov ? 'var(--surface-card-hover)' : isRunning ? 'rgba(var(--accent-rgb),.04)' : 'transparent',
        borderBottom: '1px solid var(--border-subtle)',
        cursor: 'pointer',
        transition: 'background .12s',
        position: 'relative' as const,
      }}
    >
      {/* Left accent */}
      <div style={{
        width: 3, height: 36, borderRadius: 2, flexShrink: 0,
        background: st.color,
        opacity: isRunning ? 1 : 0.7,
      }} />

      {/* Status icon */}
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: st.bg, border: `1px solid ${st.border}`,
        fontSize: 12, color: st.color, fontWeight: 700,
        animation: isRunning ? 'hist-spin 1.6s linear infinite' : 'none',
      }}>
        {st.icon}
      </div>

      {/* Title + meta */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
          marginBottom: 4,
        }}>
          {job.title || job.source_hint || `Render Job #${job.job_id.slice(0, 8)}`}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'monospace' }}>
            {job.job_id.slice(0, 8)}
          </span>
          {job.completed_count > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10,
              background: 'rgba(var(--ok-rgb),.1)', color: 'var(--ok)',
              border: '1px solid rgba(var(--ok-rgb),.2)',
            }}>
              ✓ {job.completed_count} clip{job.completed_count !== 1 ? 's' : ''}
            </span>
          )}
          {job.failed_count > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10,
              background: 'rgba(var(--fail-rgb),.1)', color: 'var(--fail)',
              border: '1px solid rgba(var(--fail-rgb),.2)',
            }}>
              ✕ {job.failed_count} failed
            </span>
          )}
          {isRunning && job.total_count > 0 && (
            <ProgressRing done={job.completed_count} total={job.total_count} color="var(--accent)" />
          )}
        </div>
      </div>

      {/* Progress bar (running) — Bug #10/#11 fix: always show when running
          (uses job.progress_percent so it works for every stage) + ETA
          label derived from elapsed × (100-pct)/pct. */}
      {isRunning && (
        <div style={{ width: 96, flexShrink: 0 }}>
          <div style={{ height: 5, borderRadius: 999, background: 'var(--surface-card-hover)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 999,
              width: `${pct}%`,
              background: 'var(--brand-gradient)',
              boxShadow: '0 0 8px rgba(139,92,246,.45)',
              transition: 'width .4s ease',
            }} />
          </div>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            marginTop: 3, gap: 4,
          }}>
            <span style={{ fontSize: 10, fontFamily: 'var(--font-family-mono)', fontWeight: 600, color: 'var(--accent-primary)' }}>
              {pct}%
            </span>
            {etaLabel && (
              <span style={{ fontSize: 9, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' as const, fontFamily: 'var(--font-family-mono)' }}>
                {etaLabel}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Date */}
      <span style={{ fontSize: 10, color: 'var(--text-3)', flexShrink: 0, whiteSpace: 'nowrap' as const, minWidth: 70, textAlign: 'right' as const }}>
        {fmtDate(job.created_at)}
      </span>

      {/* Status badge */}
      <span style={{
        fontSize: 9, fontWeight: 800, padding: '3px 9px', borderRadius: 20, flexShrink: 0,
        background: st.bg, color: st.color, border: `1px solid ${st.border}`,
        letterSpacing: '.04em',
      }}>
        {st.label.toUpperCase()}
      </span>

      {/* Row actions — Bug #3 fix: cancel button surfaces directly on running
          rows so the user can stop a runaway job from History without first
          having to navigate into the Rendering screen. */}
      {(isRunning || isQueued) && (
        <button
          onClick={(e) => { e.stopPropagation(); onCancel(job) }}
          title="Cancel render"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            height: 26, padding: '0 10px', borderRadius: 999,
            background: 'var(--status-error-bg)',
            color: 'var(--status-error)',
            border: '1px solid color-mix(in srgb, var(--status-error) 30%, transparent)',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
            flexShrink: 0, transition: 'all .12s',
            letterSpacing: '-.005em',
          }}
        >
          ✕ Cancel
        </button>
      )}

      {/* Arrow — chevron hint on hover only for non-active rows */}
      {!(isRunning || isQueued) && (
        <span style={{ fontSize: 10, color: 'var(--text-3)', opacity: hov ? 1 : 0, transition: 'opacity .1s', flexShrink: 0 }}>›</span>
      )}
    </div>
  )
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div style={{
      padding: '8px 20px 6px',
      fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
      letterSpacing: '.08em', textTransform: 'uppercase' as const,
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex', alignItems: 'center', gap: 8,
      background: 'var(--surface-base)',
    }}>
      {label}
      <span style={{ fontSize: 9, padding: '0 5px', borderRadius: 8, background: 'var(--border-subtle)', color: 'var(--text-2)' }}>
        {count}
      </span>
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

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, overflow: 'hidden', background: 'var(--surface-base)' }}>
      <style>{`
        @keyframes hist-spin { to { transform: rotate(360deg) } }
        @keyframes hist-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
      `}</style>

      {/* Header */}
      <div style={{
        padding: '18px 24px 14px',
        borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
        background: 'var(--surface-panel)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 28, height: 28, borderRadius: 8,
            background: 'var(--brand-gradient)',
            color: '#fff', flexShrink: 0,
            boxShadow: '0 1px 0 rgba(255,255,255,.3) inset, 0 2px 8px rgba(139,92,246,.35)',
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9"/>
              <path d="M12 7v5l3 2"/>
            </svg>
          </span>
          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 1 }}>
            <span style={{ fontFamily: 'var(--font-family-display)', fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-.02em', lineHeight: 1.2 }}>History</span>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>All your render jobs in one place</span>
          </div>

          <div style={{ display: 'flex', gap: 6, marginLeft: 4 }}>
            {runningCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'rgba(var(--accent-rgb),.15)', color: 'var(--accent)', border: '1px solid rgba(var(--accent-rgb),.3)' }}>
                {runningCount} running
              </span>
            )}
            {doneCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(var(--ok-rgb),.1)', color: 'var(--ok)' }}>
                {doneCount} done
              </span>
            )}
            {failedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(var(--fail-rgb),.1)', color: 'var(--fail)' }}>
                {failedCount} failed
              </span>
            )}
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              onClick={() => { refresh() }}
              title="Refresh"
              style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 14, cursor: 'pointer', padding: 4, lineHeight: 1 }}
            >
              ↻
            </button>
            <button
              onClick={handleClearHistory}
              disabled={clearing || jobs.length === 0}
              title="Clear history (keeps active jobs)"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                height: 28, padding: '0 11px', borderRadius: 'var(--radius-full)',
                border: '1px solid var(--border-default)',
                background: 'transparent',
                color: jobs.length === 0 ? 'var(--text-disabled)' : 'var(--text-2)',
                fontSize: 11, fontWeight: 600, lineHeight: 1,
                cursor: clearing || jobs.length === 0 ? 'not-allowed' : 'pointer',
                transition: 'all .12s',
              }}
              onMouseEnter={(e) => { if (!clearing && jobs.length > 0) { e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--status-error) 35%, transparent)'; e.currentTarget.style.color = 'var(--status-error)' } }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border-default)'; e.currentTarget.style.color = jobs.length === 0 ? 'var(--text-disabled)' : 'var(--text-2)' }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              </svg>
              {clearing ? 'Clearing…' : 'Clear'}
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Filter tabs */}
          <div style={{ display: 'flex', background: 'var(--surface-card)', borderRadius: 10, border: '1px solid var(--border-subtle)', padding: 3, gap: 2 }}>
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '5px 14px', borderRadius: 7, cursor: 'pointer', border: 'none',
                  background: filter === f
                    ? 'linear-gradient(135deg, rgba(139,92,246,.14), rgba(236,72,153,.12))'
                    : 'transparent',
                  color: filter === f ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  boxShadow: filter === f ? '0 0 0 1px color-mix(in srgb, var(--accent-primary) 25%, transparent) inset' : 'none',
                  fontSize: 12, fontWeight: 600,
                  transition: 'all .12s',
                  letterSpacing: '-.005em',
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <div style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
            background: 'var(--surface-panel)', border: '1px solid var(--border-default)', borderRadius: 8, padding: '0 10px',
            height: 32,
          }}>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>🔍</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              style={{
                background: 'none', border: 'none', outline: 'none',
                fontSize: 11, color: 'var(--text-1)', width: 160,
              }}
            />
          </div>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading && (
          <div style={{ padding: 40, textAlign: 'center' as const, color: 'var(--text-3)', fontSize: 12 }}>Loading…</div>
        )}
        {!loading && error && (
          <div style={{ padding: 40, textAlign: 'center' as const, color: 'var(--fail)', fontSize: 12 }}>⚠ {error}</div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 18, padding: 56, minHeight: 360 }}>
            <div
              aria-hidden="true"
              style={{
                width: 96, height: 96, borderRadius: 24,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--brand-gradient-soft)',
                border: '1px solid color-mix(in srgb, var(--accent-primary) 22%, transparent)',
                color: 'var(--accent-primary)',
                boxShadow: '0 1px 0 rgba(255,255,255,.4) inset, 0 10px 28px rgba(139,92,246,.16)',
              }}
            >
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9"/>
                <path d="M12 7v5l3 2"/>
              </svg>
            </div>
            <div style={{ textAlign: 'center' as const, maxWidth: 340, display: 'flex', flexDirection: 'column' as const, gap: 6 }}>
              <div style={{
                fontFamily: 'var(--font-family-display)', fontSize: 18, fontWeight: 600,
                color: 'var(--text-primary)', letterSpacing: '-.02em', lineHeight: 1.25,
              }}>
                {search || filter !== 'All' ? 'No matches' : 'No render jobs yet'}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
                {search || filter !== 'All'
                  ? 'Try clearing the filter or search.'
                  : 'Your finished and in-progress renders will appear here.'}
              </div>
            </div>
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (
          <>
            {today.length > 0 && (
              <>
                <SectionHeader label="Today" count={today.length} />
                {today.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} onCancel={handleCancel} onMonitor={handleMonitor} />)}
              </>
            )}
            {yesterday.length > 0 && (
              <>
                <SectionHeader label="Yesterday" count={yesterday.length} />
                {yesterday.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} onCancel={handleCancel} onMonitor={handleMonitor} />)}
              </>
            )}
            {older.length > 0 && (
              <>
                <SectionHeader label="Older" count={older.length} />
                {older.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} onCancel={handleCancel} onMonitor={handleMonitor} />)}
              </>
            )}
          </>
        )}
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
