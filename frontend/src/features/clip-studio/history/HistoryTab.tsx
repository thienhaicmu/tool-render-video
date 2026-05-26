import { useState, useEffect } from 'react'
import type { Lang } from '../ClipStudio'
import { getJobHistory } from '../../../api/jobs'
import type { HistoryItem } from '../../../types/api'

const FILTERS = ['All', 'Done', 'Failed', 'Running'] as const
type Filter = typeof FILTERS[number]

const STATUS_COLOR: Record<string, string> = {
  completed:              'var(--cs-ok)',
  completed_with_errors:  'var(--cs-warn)',
  failed:                 'var(--cs-fail)',
  running:                'var(--cs-accent)',
  queued:                 'var(--cs-text-3)',
  interrupted:            'var(--cs-warn)',
  cancelled:              'var(--cs-text-3)',
  cancelling:             'var(--cs-text-3)',
}

export function HistoryTab({ lang: _lang }: { lang: Lang }) {
  const [filter, setFilter] = useState<Filter>('All')
  const [search, setSearch] = useState('')
  const [jobs, setJobs]     = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getJobHistory(50, 0)
      .then((res) => setJobs(res.items))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load history'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = jobs.filter((j) => {
    if (filter === 'Done'    && !j.status.startsWith('completed')) return false
    if (filter === 'Failed'  && j.status !== 'failed')             return false
    if (filter === 'Running' && j.status !== 'running')            return false
    if (search && !j.job_id.includes(search) && !(j.title || '').toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--cs-bg-base)' }}>
      {/* Toolbar */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid var(--cs-border)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        flexShrink: 0,
      }}>
        {/* Filter chips */}
        <div style={{ display: 'flex', gap: '6px' }}>
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: '4px 12px',
                borderRadius: '20px',
                border: `1px solid ${filter === f ? 'var(--cs-accent)' : 'var(--cs-border)'}`,
                background: filter === f ? 'var(--cs-accent-dim)' : 'var(--cs-bg-card)',
                color: filter === f ? 'var(--cs-accent)' : 'var(--cs-text-3)',
                fontFamily: 'var(--cs-font-head)',
                fontSize: '11px',
                fontWeight: 700,
                letterSpacing: '0.5px',
                cursor: 'pointer',
                transition: 'all 150ms',
              }}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          placeholder="Search jobs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            marginLeft: 'auto',
            background: 'var(--cs-bg-card)',
            border: '1px solid var(--cs-border)',
            borderRadius: '6px',
            padding: '6px 12px',
            fontSize: '12px',
            color: 'var(--cs-text-1)',
            outline: 'none',
            width: '200px',
            fontFamily: 'var(--cs-font-body)',
          }}
        />
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--cs-text-3)', fontSize: '13px' }}>
            Loading…
          </div>
        )}
        {error && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--cs-fail)', fontSize: '13px' }}>
            {error}
          </div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '12px', color: 'var(--cs-text-3)', fontSize: '13px' }}>
            <span style={{ fontSize: '36px', opacity: 0.3 }}>📋</span>
            No render jobs found
          </div>
        )}
        {!loading && !error && filtered.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--cs-border)' }}>
                {['Job ID', 'Status', 'Title', 'Clips', 'Created'].map((h) => (
                  <th key={h} style={{
                    padding: '8px 16px',
                    textAlign: 'left',
                    fontSize: '10px',
                    fontFamily: 'var(--cs-font-head)',
                    fontWeight: 700,
                    letterSpacing: '1px',
                    textTransform: 'uppercase',
                    color: 'var(--cs-text-3)',
                    background: 'var(--cs-bg-panel)',
                    position: 'sticky',
                    top: 0,
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((job, i) => (
                <tr
                  key={job.job_id}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,.04)',
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,.01)',
                    cursor: 'pointer',
                    transition: 'background 100ms',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--cs-bg-hover)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,.01)')}
                >
                  <td style={{ padding: '8px 16px', fontSize: '11px', color: 'var(--cs-text-2)', fontFamily: 'monospace' }}>
                    {job.job_id.slice(0, 12)}…
                  </td>
                  <td style={{ padding: '8px 16px' }}>
                    <span style={{
                      fontSize: '10px',
                      fontFamily: 'var(--cs-font-head)',
                      fontWeight: 700,
                      letterSpacing: '0.5px',
                      textTransform: 'uppercase',
                      color: STATUS_COLOR[job.status] || 'var(--cs-text-3)',
                    }}>
                      {job.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td style={{ padding: '8px 16px', fontSize: '11px', color: 'var(--cs-text-2)', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {job.title || job.source_hint || '—'}
                  </td>
                  <td style={{ padding: '8px 16px', fontSize: '11px', color: 'var(--cs-text-3)' }}>
                    {job.completed_count > 0 ? (
                      <span style={{ color: 'var(--cs-ok)' }}>{job.completed_count}</span>
                    ) : '—'}
                    {job.failed_count > 0 && (
                      <span style={{ color: 'var(--cs-fail)', marginLeft: '4px' }}>/{job.failed_count} fail</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 16px', fontSize: '11px', color: 'var(--cs-text-3)' }}>
                    {new Date(job.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
