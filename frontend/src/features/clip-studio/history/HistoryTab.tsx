import { useState, useEffect, useCallback, useRef } from 'react'
import type { Lang } from '../ClipStudio'
import { getJobHistory } from '@/api/jobs'
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

function JobRow({ job, onOpen }: { job: HistoryItem; onOpen: (j: HistoryItem) => void }) {
  const st = sm(job.status)
  const isRunning = job.status === 'running'
  const [hov, setHov] = useState(false)
  const pct = isRunning && job.total_count > 0 ? Math.round((job.completed_count / job.total_count) * 100) : 0

  return (
    <div
      onClick={() => onOpen(job)}
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

      {/* Progress bar (running only) */}
      {isRunning && job.total_count > 0 && (
        <div style={{ width: 72, flexShrink: 0 }}>
          <div style={{ height: 5, borderRadius: 999, background: 'var(--surface-card-hover)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 999,
              width: `${pct}%`,
              background: 'var(--brand-gradient)',
              boxShadow: '0 0 8px rgba(139,92,246,.45)',
              transition: 'width .4s ease',
            }} />
          </div>
          <div style={{ fontSize: 10, fontFamily: 'var(--font-family-mono)', fontWeight: 600, color: 'var(--accent-primary)', textAlign: 'center' as const, marginTop: 3 }}>{pct}%</div>
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

      {/* Arrow */}
      <span style={{ fontSize: 10, color: 'var(--text-3)', opacity: hov ? 1 : 0, transition: 'opacity .1s', flexShrink: 0 }}>›</span>
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

function DetailDrawer({ job, onClose }: { job: HistoryItem; onClose: () => void }) {
  const st = sm(job.status)
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

        {/* Actions */}
        <div style={{ padding: '0 16px', marginTop: 'auto', paddingBottom: 20, display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
          {job.can_open_folder && job.output_dir && (
            <button
              onClick={() => { navigator.clipboard.writeText(job.output_dir!).catch(() => {}) }}
              style={{
                padding: '10px', borderRadius: 8, background: 'var(--surface-card-hover)',
                border: '1px solid var(--border-strong)', color: 'var(--text-1)', fontSize: 11,
                fontWeight: 600, cursor: 'pointer',
              }}
            >
              Copy output path
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

const POLL_MS = 5000

export function HistoryTab({ lang: _lang }: { lang: Lang }) {
  const [filter, setFilter]     = useState<Filter>('All')
  const [search, setSearch]     = useState('')
  const [jobs, setJobs]         = useState<HistoryItem[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [selected, setSelected] = useState<HistoryItem | null>(null)
  const pollRef                 = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await getJobHistory(100, 0)
      setJobs(res.items)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load history')
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    refresh().finally(() => setLoading(false))
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [refresh])

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

          <button
            onClick={() => { setLoading(true); refresh().finally(() => setLoading(false)) }}
            title="Refresh"
            style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 14, cursor: 'pointer', padding: 4, lineHeight: 1 }}
          >
            ↻
          </button>
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
                {today.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} />)}
              </>
            )}
            {yesterday.length > 0 && (
              <>
                <SectionHeader label="Yesterday" count={yesterday.length} />
                {yesterday.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} />)}
              </>
            )}
            {older.length > 0 && (
              <>
                <SectionHeader label="Older" count={older.length} />
                {older.map((j) => <JobRow key={j.job_id} job={j} onOpen={setSelected} />)}
              </>
            )}
          </>
        )}
      </div>

      {/* Detail drawer */}
      {selected && <DetailDrawer job={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
