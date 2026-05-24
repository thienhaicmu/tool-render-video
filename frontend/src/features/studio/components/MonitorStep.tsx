import { useState, useEffect, useRef, useCallback } from 'react'
import { getJobHistory } from '../../../api/jobs'
import { useI18n } from '../../../i18n/useI18n'
import type { HistoryItem } from '../../../types/api'

interface MonitorStepProps {
  jobId: string | null
  onComplete: () => void
}

type TabFilter = 'all' | 'rendering' | 'completed' | 'failed'

interface LivePart {
  part_no: number
  status: string
  progress_percent: number
}

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
      backgroundColor: '#a855f7',
      boxShadow: '0 0 6px rgba(168,85,247,0.7)',
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

// ── Part progress dots ────────────────────────────────────────────────────────

function PartDots({ parts }: { parts: LivePart[] }) {
  const visible = parts.slice(0, 12)
  return (
    <div style={{ display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' }}>
      {visible.map((p) => {
        const isDone = p.status === 'done' || p.status === 'completed' || p.status === 'completed_with_errors'
        const isRendering = p.status === 'rendering' || p.status === 'cutting' || p.status === 'transcribing' || p.status === 'downloading' || p.status === 'running'
        const bg = isDone ? '#34C878' : isRendering ? '#a855f7' : 'var(--border-subtle)'
        const anim = isRendering ? 'mon-pulse 1.5s ease-in-out infinite' : undefined
        return (
          <span
            key={p.part_no}
            title={`Part ${p.part_no}: ${p.status} (${p.progress_percent}%)`}
            style={{
              display: 'inline-block',
              width: '10px',
              height: '10px',
              borderRadius: '3px',
              backgroundColor: bg,
              opacity: isDone ? 1 : isRendering ? 1 : 0.35,
              animation: anim,
              flexShrink: 0,
            }}
          />
        )
      })}
      {parts.length > 12 && (
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', lineHeight: '10px' }}>
          +{parts.length - 12}
        </span>
      )}
    </div>
  )
}

// ── ETA helper ────────────────────────────────────────────────────────────────

function formatEta(sec: number): string {
  if (sec < 60) return `ETA ~${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s > 0 ? `ETA ~${m}m ${s}s` : `ETA ~${m}m`
}

// ── Job card ───────────────────────────────────────────────────────────────────

interface JobCardProps {
  item: HistoryItem
  isCurrentJob: boolean
  liveProgress: number
  liveStage: string
  liveEtaSec: number | null
  liveParts: LivePart[]
}

function JobCard({ item, isCurrentJob, liveProgress, liveStage, liveEtaSec, liveParts }: JobCardProps) {
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

  // For the current live job use WS progress; for others progress is not available
  const progressPct = isCurrentJob ? liveProgress : 0
  const stageTxt = isCurrentJob ? liveStage : ''

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
        backgroundColor: isCurrentJob ? 'rgba(168,85,247,0.05)' : hovered ? 'rgba(255,255,255,0.02)' : 'var(--surface-card)',
        border: `1px solid ${isCurrentJob ? 'rgba(168,85,247,0.2)' : hovered ? 'var(--border-default)' : 'var(--border-subtle)'}`,
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
        border: '1px solid var(--border-subtle)',
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="3"/>
          <polygon points="10 8 16 12 10 16 10 8" fill="var(--text-tertiary)" stroke="none"/>
        </svg>
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
              color: '#a855f7',
              backgroundColor: 'rgba(168,85,247,0.1)',
              border: '1px solid rgba(168,85,247,0.2)',
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
          <span style={{ fontSize: '11px', color: isRunning ? '#a855f7' : isCompleted ? '#34C878' : isFailed ? '#E05252' : 'var(--text-tertiary)', fontWeight: 500 }}>
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
          <div style={{ marginTop: '6px' }}>
            {/* Progress bar row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ flex: 1, height: '3px', borderRadius: '2px', backgroundColor: 'var(--surface-input)', overflow: 'hidden' }}>
                {isCurrentJob && progressPct > 0 ? (
                  // Real determinate bar from WS
                  <div style={{
                    height: '100%',
                    width: `${progressPct}%`,
                    background: 'linear-gradient(90deg, #a855f7, #4d7cff)',
                    borderRadius: '2px',
                    transition: 'width 0.4s ease',
                  }} />
                ) : (
                  // Indeterminate for non-current or zero progress
                  <div style={{
                    height: '100%',
                    width: '60%',
                    background: 'linear-gradient(90deg, #a855f7, #4d7cff)',
                    borderRadius: '2px',
                    animation: 'mon-slide 2s ease-in-out infinite',
                  }} />
                )}
              </div>
              {isCurrentJob && progressPct > 0 && (
                <span style={{ fontSize: '10px', color: '#a855f7', fontWeight: 600, flexShrink: 0 }}>
                  {progressPct}%
                </span>
              )}
              {/* Stage label */}
              {isCurrentJob && stageTxt ? (
                <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', flexShrink: 0 }}>{stageTxt}</span>
              ) : (
                <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', flexShrink: 0 }}>Processing…</span>
              )}
              {/* ETA */}
              {isCurrentJob && liveEtaSec !== null && liveEtaSec > 0 && (
                <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', flexShrink: 0 }}>
                  {formatEta(liveEtaSec)}
                </span>
              )}
            </div>

            {/* Per-part dots (only for current live job) */}
            {isCurrentJob && liveParts.length > 0 && (
              <PartDots parts={liveParts} />
            )}
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
    height: '34px',
    padding: '0 14px',
    border: '1px solid rgba(52,200,120,0.4)',
    borderRadius: '8px',
    backgroundColor: 'rgba(52,200,120,0.08)',
    color: '#34C878',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  cancelBtn: {
    height: '34px',
    padding: '0 14px',
    border: '1px solid var(--border-default)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
}

// ── MonitorStep ───────────────────────────────────────────────────────────────

const TERMINAL_STATUSES = new Set(['completed', 'completed_with_errors', 'failed', 'cancelled', 'interrupted'])

export function MonitorStep({ jobId, onComplete }: MonitorStepProps) {
  const { t } = useI18n()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [tab, setTab] = useState<TabFilter>('all')

  // WebSocket live state
  const wsRef = useRef<WebSocket | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('')
  const [etaSec, setEtaSec] = useState<number | null>(null)
  const [liveParts, setLiveParts] = useState<LivePart[]>([])

  // HTTP polling refs
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wsFallbackActiveRef = useRef(false)

  const poll = useCallback(async () => {
    try {
      const res = await getJobHistory(10, 0)
      setItems(res.items)
    } catch { /* ignore */ }
  }, [])

  // HTTP fallback polling — only started when WS fails
  const startHttpFallback = useCallback(() => {
    if (wsFallbackActiveRef.current) return
    wsFallbackActiveRef.current = true
    poll()
    intervalRef.current = setInterval(poll, 2000)
  }, [poll])

  // Stop HTTP polling
  const stopHttpPoll = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    wsFallbackActiveRef.current = false
  }, [])

  // WebSocket connection for live job progress
  useEffect(() => {
    if (!jobId) return

    const wsUrl = `ws://127.0.0.1:8000/api/jobs/${jobId}/ws`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      // WS is live — ensure HTTP poll is not also running for redundancy
      stopHttpPoll()
      // Kick one HTTP poll for the job list sidebar
      poll()
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string)
        const summary = data.summary ?? {}
        const pct: number = summary.overall_progress_percent ?? data.job?.progress_percent ?? 0
        setProgress(pct)
        setStage(summary.current_stage ?? data.job?.stage ?? '')
        setEtaSec(typeof summary.eta_seconds === 'number' ? summary.eta_seconds : null)
        if (Array.isArray(data.parts)) setLiveParts(data.parts as LivePart[])

        const status: string = summary.status ?? data.job?.status ?? ''
        if (TERMINAL_STATUSES.has(status)) {
          ws.close()
          // Refresh job list after terminal state
          poll()
          if (status === 'completed' || status === 'completed_with_errors') {
            onComplete()
          }
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onerror = () => {
      setWsConnected(false)
      startHttpFallback()
    }

    ws.onclose = () => {
      setWsConnected(false)
    }

    return () => {
      ws.close()
    }
  }, [jobId, onComplete, poll, startHttpFallback, stopHttpPoll])

  // Always keep job list refreshed via HTTP polling unless WS is connected
  useEffect(() => {
    // Initial poll immediately
    poll()

    // If no jobId (no active WS), start HTTP poll normally
    if (!jobId) {
      intervalRef.current = setInterval(poll, 2000)
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }

    // If there is a jobId, the WS effect above handles polling control
    return () => {
      stopHttpPoll()
    }
  }, [jobId, poll, stopHttpPoll])

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
            {wsConnected ? (
              <div style={s.liveBadge}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#34C878', animation: 'mon-pulse 1.5s ease-in-out infinite' }} />
                <span>Live</span>
              </div>
            ) : countRendering > 0 ? (
              <div style={{ ...s.liveBadge, color: 'var(--text-tertiary)', backgroundColor: 'var(--surface-input)', border: '1px solid var(--border-subtle)' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--text-tertiary)' }} />
                <span>Polling</span>
              </div>
            ) : null}
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
                borderBottom: tab === t_.id ? '2px solid #a855f7' : '2px solid transparent',
                fontWeight: tab === t_.id ? 600 : 400,
              }}
            >
              {t_.label}
              {t_.count > 0 && (
                <span style={{
                  marginLeft: '5px',
                  fontSize: '10px',
                  fontWeight: 700,
                  color: tab === t_.id ? '#a855f7' : 'var(--text-tertiary)',
                  backgroundColor: tab === t_.id ? 'rgba(168,85,247,0.12)' : 'var(--surface-input)',
                  padding: '0 5px',
                  borderRadius: '8px',
                  border: `1px solid ${tab === t_.id ? 'rgba(168,85,247,0.2)' : 'var(--border-subtle)'}`,
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
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.15, color: 'var(--text-tertiary)' }}>
                <rect x="2" y="2" width="20" height="20" rx="3"/>
                <polygon points="10 8 16 12 10 16 10 8"/>
              </svg>
              <span style={s.emptyText}>No jobs in this category.</span>
            </div>
          ) : (
            filtered.map((item) => (
              <JobCard
                key={item.job_id}
                item={item}
                isCurrentJob={item.job_id === jobId}
                liveProgress={progress}
                liveStage={stage}
                liveEtaSec={etaSec}
                liveParts={liveParts}
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
    height: '48px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    backgroundColor: 'var(--surface-panel)',
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
    backgroundColor: 'rgba(52,200,120,0.1)',
    border: '1px solid rgba(52,200,120,0.25)',
    fontSize: '11px',
    fontWeight: 700,
    color: '#34C878',
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
    backgroundColor: 'var(--surface-panel)',
  },
  tabBtn: {
    height: '44px',
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
    padding: '0 20px',
    border: 'none',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
    color: '#fff',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 0 0 1px rgba(168,85,247,.35), 0 0 16px rgba(168,85,247,.2)',
    transition: 'opacity 0.15s ease',
  },
}
