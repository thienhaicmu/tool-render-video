import { useState, useEffect, useCallback, useRef } from 'react'
import type { Lang } from '../ClipStudio'
import { getJobHistory } from '@/api/jobs'
import type { HistoryItem } from '@/types/api'

const FILTERS = ['All', 'Done', 'Failed', 'Running'] as const
type Filter = typeof FILTERS[number]

const S: Record<string, { color: string; bg: string; border: string; label: string; icon: string }> = {
  completed:             { color: '#00C896', bg: 'rgba(0,200,150,.12)',   border: 'rgba(0,200,150,.25)',   label: 'Done',        icon: '✓' },
  completed_with_errors: { color: '#F0A020', bg: 'rgba(240,160,32,.12)',  border: 'rgba(240,160,32,.25)',  label: 'Partial',     icon: '⚠' },
  failed:                { color: '#E8407A', bg: 'rgba(232,64,122,.12)',  border: 'rgba(232,64,122,.25)',  label: 'Failed',      icon: '✕' },
  running:               { color: '#7B61FF', bg: 'rgba(123,97,255,.12)',  border: 'rgba(123,97,255,.3)',   label: 'Running',     icon: '⟳' },
  queued:                { color: '#8A93B0', bg: 'rgba(138,147,176,.10)', border: 'rgba(138,147,176,.2)',  label: 'Queued',      icon: '○' },
  interrupted:           { color: '#F0A020', bg: 'rgba(240,160,32,.12)',  border: 'rgba(240,160,32,.25)',  label: 'Interrupted', icon: '!' },
  cancelled:             { color: '#4A5270', bg: 'rgba(74,82,112,.10)',   border: 'rgba(74,82,112,.2)',    label: 'Cancelled',   icon: '—' },
  cancelling:            { color: '#4A5270', bg: 'rgba(74,82,112,.10)',   border: 'rgba(74,82,112,.2)',    label: 'Cancelling',  icon: '…' },
}
const sm = (s: string) => S[s] ?? { color: '#8A93B0', bg: 'rgba(138,147,176,.10)', border: 'rgba(138,147,176,.2)', label: s.replace(/_/g, ' '), icon: '?' }

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
        background: hov ? '#161C2C' : isRunning ? 'rgba(123,97,255,.04)' : 'transparent',
        borderBottom: '1px solid rgba(255,255,255,.04)',
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
          fontSize: 12, fontWeight: 600, color: '#EEF0F8',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
          marginBottom: 4,
        }}>
          {job.title || job.source_hint || `Render Job #${job.job_id.slice(0, 8)}`}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }}>
          <span style={{ fontSize: 10, color: '#4A5270', fontFamily: 'monospace' }}>
            {job.job_id.slice(0, 8)}
          </span>
          {job.completed_count > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10,
              background: 'rgba(0,200,150,.1)', color: '#00C896',
              border: '1px solid rgba(0,200,150,.2)',
            }}>
              ✓ {job.completed_count} clip{job.completed_count !== 1 ? 's' : ''}
            </span>
          )}
          {job.failed_count > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10,
              background: 'rgba(232,64,122,.1)', color: '#E8407A',
              border: '1px solid rgba(232,64,122,.2)',
            }}>
              ✕ {job.failed_count} failed
            </span>
          )}
          {isRunning && job.total_count > 0 && (
            <ProgressRing done={job.completed_count} total={job.total_count} color="#7B61FF" />
          )}
        </div>
      </div>

      {/* Progress bar (running only) */}
      {isRunning && job.total_count > 0 && (
        <div style={{ width: 64, flexShrink: 0 }}>
          <div style={{ height: 4, borderRadius: 2, background: 'rgba(123,97,255,.15)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 2,
              width: `${pct}%`,
              background: 'linear-gradient(90deg,#7B61FF,#00E5C8)',
              transition: 'width .4s ease',
            }} />
          </div>
          <div style={{ fontSize: 9, color: '#7B61FF', textAlign: 'center' as const, marginTop: 2 }}>{pct}%</div>
        </div>
      )}

      {/* Date */}
      <span style={{ fontSize: 10, color: '#4A5270', flexShrink: 0, whiteSpace: 'nowrap' as const, minWidth: 70, textAlign: 'right' as const }}>
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
      <span style={{ fontSize: 10, color: '#4A5270', opacity: hov ? 1 : 0, transition: 'opacity .1s', flexShrink: 0 }}>›</span>
    </div>
  )
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div style={{
      padding: '8px 20px 6px',
      fontSize: 10, fontWeight: 700, color: '#4A5270',
      letterSpacing: '.08em', textTransform: 'uppercase' as const,
      borderBottom: '1px solid rgba(255,255,255,.04)',
      display: 'flex', alignItems: 'center', gap: 8,
      background: '#090C13',
    }}>
      {label}
      <span style={{ fontSize: 9, padding: '0 5px', borderRadius: 8, background: 'rgba(255,255,255,.06)', color: '#8A93B0' }}>
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
          background: '#111622',
          borderLeft: '1px solid #1C2438',
          display: 'flex', flexDirection: 'column' as const,
          boxShadow: '-12px 0 48px rgba(0,0,0,.6)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #1C2438', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#EEF0F8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
              {job.title || job.source_hint || 'Render Job'}
            </div>
            <div style={{ fontSize: 10, color: '#4A5270', marginTop: 2, fontFamily: 'monospace' }}>#{job.job_id}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#4A5270', fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}>×</button>
        </div>

        {/* Stats grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: '#1C2438', margin: 16, borderRadius: 10, overflow: 'hidden' }}>
          {[
            { label: 'Status', value: st.label, color: st.color },
            { label: 'Clips done', value: `${job.completed_count}`, color: '#00C896' },
            { label: 'Failed', value: `${job.failed_count}`, color: job.failed_count > 0 ? '#E8407A' : '#4A5270' },
            { label: 'Total', value: `${job.total_count}`, color: '#EEF0F8' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: '#111622', padding: '12px 14px' }}>
              <div style={{ fontSize: 9, color: '#4A5270', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Summary text */}
        {job.summary_text && (
          <div style={{ padding: '0 16px 16px' }}>
            <div style={{ fontSize: 10, color: '#4A5270', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 6 }}>Summary</div>
            <div style={{ fontSize: 11, color: '#8A93B0', lineHeight: 1.6, background: '#0D1019', padding: '10px 12px', borderRadius: 8, border: '1px solid #1C2438' }}>
              {job.summary_text}
            </div>
          </div>
        )}

        {/* Output dir */}
        {job.output_dir && (
          <div style={{ padding: '0 16px 16px' }}>
            <div style={{ fontSize: 10, color: '#4A5270', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 6 }}>Output folder</div>
            <div style={{
              fontSize: 10, color: '#8A93B0', fontFamily: 'monospace',
              background: '#0D1019', padding: '8px 10px', borderRadius: 6,
              border: '1px solid #1C2438', wordBreak: 'break-all' as const,
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
                padding: '10px', borderRadius: 8, background: '#161C2C',
                border: '1px solid #2A3558', color: '#EEF0F8', fontSize: 11,
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
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' as const, overflow: 'hidden', background: '#090C13' }}>
      <style>{`
        @keyframes hist-spin { to { transform: rotate(360deg) } }
        @keyframes hist-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
      `}</style>

      {/* Header */}
      <div style={{
        padding: '14px 20px 12px',
        borderBottom: '1px solid #1C2438',
        flexShrink: 0,
        background: '#0D1019',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#EEF0F8', letterSpacing: '-.01em' }}>History</span>

          <div style={{ display: 'flex', gap: 6, marginLeft: 4 }}>
            {runningCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'rgba(123,97,255,.15)', color: '#7B61FF', border: '1px solid rgba(123,97,255,.3)' }}>
                {runningCount} running
              </span>
            )}
            {doneCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(0,200,150,.1)', color: '#00C896' }}>
                {doneCount} done
              </span>
            )}
            {failedCount > 0 && (
              <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'rgba(232,64,122,.1)', color: '#E8407A' }}>
                {failedCount} failed
              </span>
            )}
          </div>

          <button
            onClick={() => { setLoading(true); refresh().finally(() => setLoading(false)) }}
            title="Refresh"
            style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#4A5270', fontSize: 14, cursor: 'pointer', padding: 4, lineHeight: 1 }}
          >
            ↻
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Filter tabs */}
          <div style={{ display: 'flex', background: '#0D1019', borderRadius: 8, border: '1px solid #1C2438', padding: 2, gap: 2 }}>
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '4px 12px', borderRadius: 6, cursor: 'pointer', border: 'none',
                  background: filter === f ? '#1B2235' : 'transparent',
                  color: filter === f ? '#EEF0F8' : '#4A5270',
                  fontSize: 11, fontWeight: 700,
                  transition: 'all .12s',
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <div style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
            background: '#0D1019', border: '1px solid #1C2438', borderRadius: 8, padding: '0 10px',
            height: 32,
          }}>
            <span style={{ fontSize: 11, color: '#4A5270' }}>🔍</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              style={{
                background: 'none', border: 'none', outline: 'none',
                fontSize: 11, color: '#EEF0F8', width: 160,
              }}
            />
          </div>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading && (
          <div style={{ padding: 40, textAlign: 'center' as const, color: '#4A5270', fontSize: 12 }}>Loading…</div>
        )}
        {!loading && error && (
          <div style={{ padding: 40, textAlign: 'center' as const, color: '#E8407A', fontSize: 12 }}>⚠ {error}</div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ padding: 60, textAlign: 'center' as const, color: '#4A5270' }}>
            <div style={{ fontSize: 32, marginBottom: 12, opacity: .3 }}>📋</div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>No jobs found</div>
            <div style={{ fontSize: 11, opacity: .6 }}>
              {search || filter !== 'All' ? 'Try adjusting your filter' : 'Render jobs will appear here'}
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
