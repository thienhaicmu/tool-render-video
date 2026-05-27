import { useState, useEffect, useCallback, useRef } from 'react'
import type { Lang } from '../ClipStudio'
import { getJobHistory } from '../../../api/jobs'
import type { HistoryItem } from '../../../types/api'

const FILTERS = ['All', 'Done', 'Failed', 'Running'] as const
type Filter = typeof FILTERS[number]

const STATUS_META: Record<string, { color: string; bg: string; label: string }> = {
  completed:             { color: '#34C878', bg: 'rgba(52,200,120,.12)',  label: 'Done' },
  completed_with_errors: { color: '#f59e0b', bg: 'rgba(245,158,11,.12)', label: 'Partial' },
  failed:                { color: '#ef4444', bg: 'rgba(239,68,68,.12)',   label: 'Failed' },
  running:               { color: '#a855f7', bg: 'rgba(168,85,247,.12)', label: 'Running' },
  queued:                { color: '#6b7280', bg: 'rgba(107,114,128,.12)', label: 'Queued' },
  interrupted:           { color: '#f59e0b', bg: 'rgba(245,158,11,.12)', label: 'Interrupted' },
  cancelled:             { color: '#6b7280', bg: 'rgba(107,114,128,.12)', label: 'Cancelled' },
  cancelling:            { color: '#6b7280', bg: 'rgba(107,114,128,.12)', label: 'Cancelling' },
}

function statusMeta(status: string) {
  return STATUS_META[status] ?? { color: '#6b7280', bg: 'rgba(107,114,128,.12)', label: status.replace(/_/g, ' ') }
}

function JobCard({ job }: { job: HistoryItem }) {
  const st = statusMeta(job.status)
  const isRunning = job.status === 'running'
  const hasFailed = job.failed_count > 0

  return (
    <div style={{
      display: 'flex',
      borderRadius: 10,
      overflow: 'hidden',
      background: 'var(--bg-card)',
      border: `1px solid ${isRunning ? 'rgba(168,85,247,.25)' : 'var(--border)'}`,
      boxShadow: isRunning ? '0 0 12px rgba(168,85,247,.08)' : 'none',
      transition: 'border-color .15s',
    }}>
      {/* Status accent bar */}
      <div style={{ width: 3, flexShrink: 0, background: `linear-gradient(180deg,${st.color},${st.color}55)` }} />

      <div style={{ flex: 1, padding: '10px 12px', minWidth: 0 }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          {/* Job ID */}
          <span style={{
            fontSize: 10, fontWeight: 700, fontFamily: 'monospace',
            color: 'var(--text-3)', flexShrink: 0,
          }}>
            #{job.job_id.slice(0, 8)}
          </span>

          {/* Title */}
          <span style={{
            flex: 1, fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {job.title || job.source_hint || '—'}
          </span>

          {/* Status badge */}
          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20, flexShrink: 0,
            background: st.bg, color: st.color,
            animation: isRunning ? 'hist-pulse 1.4s ease-in-out infinite' : 'none',
          }}>
            {st.label}
          </span>
        </div>

        {/* Stats row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
          {job.completed_count > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              background: 'rgba(52,200,120,.1)', color: '#34C878',
            }}>
              ✓ {job.completed_count} clip{job.completed_count !== 1 ? 's' : ''}
            </span>
          )}
          {hasFailed && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              background: 'rgba(239,68,68,.1)', color: '#ef4444',
            }}>
              ✕ {job.failed_count} failed
            </span>
          )}
          {job.completed_count === 0 && !hasFailed && (
            <span style={{ fontSize: 10, color: 'var(--text-3)' }}>No clips</span>
          )}
          <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 'auto' }}>
            {new Date(job.created_at).toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  )
}

const POLL_MS = 5000

export function HistoryTab({ lang: _lang }: { lang: Lang }) {
  const [filter, setFilter]   = useState<Filter>('All')
  const [search, setSearch]   = useState('')
  const [jobs, setJobs]       = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const pollRef               = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await getJobHistory(50, 0)
      setJobs(res.items)
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
      const inId    = j.job_id.toLowerCase().includes(q)
      const inTitle = (j.title || j.source_hint || '').toLowerCase().includes(q)
      if (!inId && !inTitle) return false
    }
    return true
  })

  const runningCount = jobs.filter((j) => j.status === 'running').length
  const doneCount    = jobs.filter((j) => j.status.startsWith('completed')).length
  const failedCount  = jobs.filter((j) => j.status === 'failed').length

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-base)' }}>
      <style>{`@keyframes hist-pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>

      {/* ── Header ── */}
      <div style={{
        padding: '14px 20px 12px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        background: 'linear-gradient(180deg,rgba(77,124,255,.04) 0%,transparent 100%)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>📋 History</span>
          <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
            {runningCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'rgba(168,85,247,.12)', color: '#a855f7', border: '1px solid rgba(168,85,247,.2)' }}>
                {runningCount} running
              </span>
            )}
            {doneCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(52,200,120,.1)', color: '#34C878' }}>
                {doneCount} done
              </span>
            )}
            {failedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(239,68,68,.1)', color: '#ef4444' }}>
                {failedCount} failed
              </span>
            )}
          </div>
        </div>

        {/* Filter + search row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', gap: 5 }}>
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '4px 10px', borderRadius: 20, cursor: 'pointer',
                  border: `1px solid ${filter === f ? 'rgba(168,85,247,.5)' : 'var(--border)'}`,
                  background: filter === f ? 'rgba(168,85,247,.12)' : 'var(--bg-card)',
                  color: filter === f ? '#a855f7' : 'var(--text-3)',
                  fontSize: 11, fontWeight: 700,
                }}
              >
                {f}
              </button>
            ))}
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search jobs…"
            style={{
              marginLeft: 'auto', height: 28, padding: '0 10px',
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 11, color: 'var(--text-1)',
              outline: 'none', width: 180,
            }}
          />
        </div>
      </div>

      {/* ── Job list ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 13 }}>
            Loading…
          </div>
        )}
        {!loading && error && (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ef4444', fontSize: 13 }}>
            ⚠ {error}
          </div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, color: 'var(--text-3)' }}>
            <span style={{ fontSize: 36, opacity: .2 }}>📋</span>
            <span style={{ fontSize: 13 }}>No render jobs found</span>
          </div>
        )}
        {!loading && !error && filtered.map((job) => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </div>
    </div>
  )
}
