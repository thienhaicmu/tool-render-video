import { useState, useEffect, useRef } from 'react'
import { getJobHistory } from '../../../api/jobs'
import { useI18n } from '../../../i18n/useI18n'
import type { HistoryItem } from '../../../types/api'

interface MonitorStepProps {
  jobId: string | null
  onComplete: () => void
}

type TabFilter = 'all' | 'rendering' | 'completed' | 'failed'

// ── Status icon ────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const isRunning = status === 'running' || status === 'queued'
  const isDone = status === 'completed' || status === 'completed_with_errors'
  const isFailed = status === 'failed' || status === 'cancelled'

  if (isRunning) return (
    <span style={{
      display: 'inline-block',
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      backgroundColor: '#7B61FF',
      boxShadow: '0 0 6px rgba(123,97,255,0.7)',
      animation: 'mon-pulse 2s ease-in-out infinite',
    }} />
  )
  if (isDone) return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '18px',
      height: '18px',
      borderRadius: '50%',
      backgroundColor: 'rgba(52,200,120,0.15)',
      border: '1.5px solid rgba(52,200,120,0.4)',
      color: '#34C878',
      fontSize: '9px',
      fontWeight: 800,
    }}>✓</span>
  )
  if (isFailed) return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '18px',
      height: '18px',
      borderRadius: '50%',
      backgroundColor: 'rgba(224,82,82,0.12)',
      border: '1.5px solid rgba(224,82,82,0.35)',
      color: '#E05252',
      fontSize: '10px',
    }}>✕</span>
  )
  return null
}

// ── Job card ───────────────────────────────────────────────────────────────────

function JobCard({ item, isCurrentJob }: { item: HistoryItem; isCurrentJob: boolean }) {
  const [hovered, setHovered] = useState(false)
  const isRunning = item.status === 'running' || item.status === 'queued'
  const isCompleted = item.status === 'completed' || item.status === 'completed_with_errors'
  const isFailed = item.status === 'failed' || item.status === 'cancelled'

  const statusLabel = item.status === 'queued' ? 'Queued'
    : item.status === 'running' ? 'Rendering'
    : item.status === 'completed' ? 'Completed'
    : item.status === 'completed_with_errors' ? 'Completed'
    : item.status === 'failed' ? 'Failed'
    : 'Cancelled'

  const openFolder = async () => {
    const api = (window as any).electronAPI
    if (api?.openPath && item.output_dir) await api.openPath(item.output_dir)
  }

  const cancelJob = async () => {
    try {
      await fetch(`/api/render/${encodeURIComponent(item.job_id)}/cancel`, { method: 'POST' })
    } catch { /* ignore */ }
  }

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-3) var(--space-4)',
        backgroundColor: isCurrentJob ? 'rgba(123,97,255,0.05)' : hovered ? 'rgba(255,255,255,0.02)' : 'var(--surface-card)',
        border: `1px solid ${isCurrentJob ? 'rgba(123,97,255,0.2)' : hovered ? 'var(--border-default)' : 'var(--border-subtle)'}`,
        borderRadius: '12px',
        transition: 'all 0.15s ease',
      }}
    >
      {/* Thumb */}
      <div style={{
        width: '44px',
        height: '44px',
        borderRadius: '10px',
        backgroundColor: 'var(--surface-input)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: '20px',
        color: 'var(--text-tertiary)',
      }}>
        🎬
      </div>

      {/* Main */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: '4px' }}>
          <span style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap' as const,
          }}>
            {(item.title || item.source_hint || 'Untitled').slice(0, 52)}
          </span>
          {isCurrentJob && (
            <span style={{
              fontSize: '9px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase' as const,
              color: '#7B61FF',
              backgroundColor: 'rgba(123,97,255,0.1)',
              border: '1px solid rgba(123,97,255,0.2)',
              padding: '1px 6px',
              borderRadius: '5px',
              flexShrink: 0,
            }}>
              Current
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusDot status={item.status} />
          <span style={{ fontSize: '11px', color: isRunning ? '#7B61FF' : isCompleted ? '#34C878' : isFailed ? '#E05252' : 'var(--text-tertiary)', fontWeight: 500 }}>
            {statusLabel}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
            · {item.total_count} clip{item.total_count !== 1 ? 's' : ''}
          </span>
          {item.summary_text && (
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>· {item.summary_text}</span>
          )}
        </div>

        {isRunning && (
          <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ flex: 1, height: '3px', borderRadius: '2px', backgroundColor: 'var(--surface-input)', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: '60%',
                background: 'linear-gradient(90deg, #7B61FF, #4D7CFF)',
                borderRadius: '2px',
                animation: 'mon-slide 2s ease-in-out infinite',
              }} />
            </div>
            <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', flexShrink: 0 }}>Processing…</span>
          </div>
        )}

        {isCompleted && item.completed_count > 0 && (
          <div style={{ marginTop: '4px', fontSize: '11px', color: '#34C878' }}>
            {item.completed_count} rendered{item.failed_count > 0 ? ` · ${item.failed_count} failed` : ''}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
        {isCompleted && item.can_open_folder && (
          <button onClick={openFolder} style={jc.openBtn}>Open</button>
        )}
        {isRunning && (
          <button onClick={cancelJob} style={jc.cancelBtn}>Cancel</button>
        )}
      </div>
    </div>
  )
}

const jc: Record<string, React.CSSProperties> = {
  openBtn: {
    height: '28px',
    padding: '0 12px',
    border: '1px solid rgba(52,200,120,0.4)',
    borderRadius: '8px',
    backgroundColor: 'rgba(52,200,120,0.08)',
    color: '#34C878',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  cancelBtn: {
    height: '28px',
    padding: '0 12px',
    border: '1px solid var(--border-subtle)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: '11px',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
}

// ── MonitorStep ───────────────────────────────────────────────────────────────

export function MonitorStep({ jobId, onComplete }: MonitorStepProps) {
  const { t } = useI18n()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [tab, setTab] = useState<TabFilter>('all')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    try {
      const res = await getJobHistory(10, 0)
      setItems(res.items)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    poll()
    intervalRef.current = setInterval(poll, 2000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const clearCompleted = () => {
    setItems((prev) => prev.filter((i) => i.status !== 'completed' && i.status !== 'completed_with_errors'))
  }

  const filtered = items.filter((item) => {
    if (tab === 'all') return true
    if (tab === 'rendering') return item.status === 'running' || item.status === 'queued'
    if (tab === 'completed') return item.status === 'completed' || item.status === 'completed_with_errors'
    if (tab === 'failed') return item.status === 'failed' || item.status === 'cancelled'
    return true
  })

  const countAll = items.length
  const countRendering = items.filter((i) => i.status === 'running' || i.status === 'queued').length
  const countCompleted = items.filter((i) => i.status === 'completed' || i.status === 'completed_with_errors').length
  const countFailed = items.filter((i) => i.status === 'failed' || i.status === 'cancelled').length

  const currentJobDone = jobId
    ? items.some((i) => i.job_id === jobId && (i.status === 'completed' || i.status === 'completed_with_errors'))
    : false

  const TABS: Array<{ id: TabFilter; label: string; count: number }> = [
    { id: 'all',       label: t('monitor_tab_all'),       count: countAll },
    { id: 'rendering', label: t('monitor_tab_rendering'), count: countRendering },
    { id: 'completed', label: t('monitor_tab_completed'), count: countCompleted },
    { id: 'failed',    label: t('monitor_tab_failed'),    count: countFailed },
  ]

  return (
    <>
      <style>{`
        @keyframes mon-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        @keyframes mon-slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(200%); } }
      `}</style>

      <div style={s.page}>
        {/* Header */}
        <div style={s.header}>
          <div style={s.headerLeft}>
            <span style={s.headerTitle}>{t('monitor_queue')}</span>
            {countRendering > 0 && (
              <div style={s.liveBadge}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#7B61FF', animation: 'mon-pulse 1.5s ease-in-out infinite' }} />
                <span>Live</span>
              </div>
            )}
          </div>
          <button onClick={clearCompleted} style={s.clearBtn}>
            {t('monitor_clear')}
          </button>
        </div>

        {/* Tabs */}
        <div style={s.tabs}>
          {TABS.map((t_) => (
            <button
              key={t_.id}
              onClick={() => setTab(t_.id)}
              style={{
                ...s.tabBtn,
                color: tab === t_.id ? 'var(--text-primary)' : 'var(--text-tertiary)',
                borderBottom: tab === t_.id ? '2px solid #7B61FF' : '2px solid transparent',
                fontWeight: tab === t_.id ? 600 : 400,
              }}
            >
              {t_.label}
              {t_.count > 0 && (
                <span style={{
                  marginLeft: '5px',
                  fontSize: '10px',
                  fontWeight: 700,
                  color: tab === t_.id ? '#7B61FF' : 'var(--text-tertiary)',
                  backgroundColor: tab === t_.id ? 'rgba(123,97,255,0.12)' : 'var(--surface-input)',
                  padding: '0 5px',
                  borderRadius: '8px',
                  border: `1px solid ${tab === t_.id ? 'rgba(123,97,255,0.2)' : 'var(--border-subtle)'}`,
                }}>
                  {t_.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Job list */}
        <div style={s.list}>
          {filtered.length === 0 ? (
            <div style={s.empty}>
              <span style={{ fontSize: '32px', opacity: 0.15 }}>🎬</span>
              <span style={s.emptyText}>No jobs in this category.</span>
            </div>
          ) : (
            filtered.map((item) => (
              <JobCard
                key={item.job_id}
                item={item}
                isCurrentJob={item.job_id === jobId}
              />
            ))
          )}
        </div>

        {/* View results footer */}
        {currentJobDone && (
          <div style={s.successFooter}>
            <div style={s.successMessage}>
              <span style={{ fontSize: '18px' }}>✓</span>
              <div>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: '#34C878' }}>Render Complete</div>
                <div style={{ fontSize: '11px', color: 'rgba(52,200,120,0.7)' }}>Your videos are ready to view</div>
              </div>
            </div>
            <button onClick={onComplete} style={s.viewResultsBtn}>
              {t('monitor_continue')} →
            </button>
          </div>
        )}
      </div>
    </>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-base)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-6)',
    height: '52px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  headerTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  liveBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '3px 10px',
    borderRadius: '20px',
    backgroundColor: 'rgba(123,97,255,0.1)',
    border: '1px solid rgba(123,97,255,0.2)',
    fontSize: '11px',
    fontWeight: 700,
    color: '#7B61FF',
    letterSpacing: '0.04em',
  },
  clearBtn: {
    height: '28px',
    padding: '0 var(--space-3)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: '11px',
    cursor: 'pointer',
  },
  tabs: {
    display: 'flex',
    gap: '2px',
    padding: '0 var(--space-6)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-card)',
  },
  tabBtn: {
    height: '42px',
    padding: '0 var(--space-3)',
    border: 'none',
    borderTop: '2px solid transparent',
    backgroundColor: 'transparent',
    fontSize: 'var(--text-xs)',
    cursor: 'pointer',
    transition: 'color 0.12s ease',
    display: 'flex',
    alignItems: 'center',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-4) var(--space-6)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-3)',
    padding: 'var(--space-10)',
  },
  emptyText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
  },
  successFooter: {
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-4) var(--space-6)',
    borderTop: '1px solid rgba(52,200,120,0.2)',
    backgroundColor: 'rgba(52,200,120,0.06)',
  },
  successMessage: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    color: '#34C878',
    fontSize: '22px',
  },
  viewResultsBtn: {
    height: '38px',
    padding: '0 var(--space-6)',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 3px 10px rgba(123,97,255,0.3)',
  },
}
