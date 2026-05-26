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

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatEta(sec: number): string {
  if (sec < 60) return `~${sec}s left`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s > 0 ? `~${m}m ${s}s left` : `~${m}m left`
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

// ── Pipeline stage track ───────────────────────────────────────────────────────

const PIPELINE_STAGES: Array<{ keys: string[]; label: string; short: string }> = [
  { keys: ['starting', 'queued', 'downloading'], label: 'Preparing',  short: 'Prep' },
  { keys: ['scene_detection', 'segment_building'], label: 'Analyzing', short: 'Analyze' },
  { keys: ['transcribing_full'],                   label: 'Transcript', short: 'Transcript' },
  { keys: ['rendering', 'rendering_parallel'],     label: 'Rendering',  short: 'Render' },
  { keys: ['writing_report', 'done', 'completed', 'completed_with_errors'], label: 'Done', short: 'Done' },
]

function resolveStageIdx(stage: string): number {
  const s = (stage || '').toLowerCase()
  for (let i = PIPELINE_STAGES.length - 1; i >= 0; i--) {
    if (PIPELINE_STAGES[i].keys.some((k) => s.includes(k))) return i
  }
  return 0
}

function PipelineTrack({ stage, done }: { stage: string; done: boolean }) {
  const activeIdx = done ? PIPELINE_STAGES.length - 1 : resolveStageIdx(stage)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0', marginBottom: '16px' }}>
      {PIPELINE_STAGES.map((ps, i) => {
        const isPast   = i < activeIdx
        const isActive = i === activeIdx
        const lineColor = isPast ? '#a855f7' : 'var(--border-subtle)'
        return (
          <div key={ps.label} style={{ display: 'flex', alignItems: 'center', flex: i < PIPELINE_STAGES.length - 1 ? 1 : 0 }}>
            {/* Step node */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '10px',
                fontWeight: 800,
                backgroundColor: isPast
                  ? 'rgba(168,85,247,0.15)'
                  : isActive
                  ? done ? 'rgba(52,200,120,0.15)' : 'rgba(168,85,247,0.2)'
                  : 'var(--surface-input)',
                border: `2px solid ${isPast ? 'rgba(168,85,247,0.5)' : isActive ? (done ? '#34C878' : '#a855f7') : 'var(--border-subtle)'}`,
                color: isPast ? '#a855f7' : isActive ? (done ? '#34C878' : '#a855f7') : 'var(--text-tertiary)',
                boxShadow: isActive && !done ? '0 0 10px rgba(168,85,247,0.35)' : 'none',
                animation: isActive && !done ? 'mon-pulse 2s ease-in-out infinite' : 'none',
                transition: 'all 0.3s ease',
              }}>
                {isPast ? '✓' : i + 1}
              </div>
              <span style={{
                fontSize: '9px',
                fontWeight: isActive ? 700 : 500,
                color: isPast ? '#a855f7' : isActive ? (done ? '#34C878' : '#a855f7') : 'var(--text-tertiary)',
                letterSpacing: '0.03em',
                textTransform: 'uppercase' as const,
                whiteSpace: 'nowrap' as const,
              }}>
                {ps.short}
              </span>
            </div>
            {/* Connector line */}
            {i < PIPELINE_STAGES.length - 1 && (
              <div style={{
                flex: 1,
                height: '2px',
                backgroundColor: lineColor,
                marginTop: '-14px',
                transition: 'background-color 0.3s ease',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Per-clip step config ───────────────────────────────────────────────────────

interface StepStyle { label: string; color: string; bg: string; pulse?: boolean }

const STEP_STYLES: Record<string, StepStyle> = {
  queued:       { label: 'Waiting',    color: 'var(--text-tertiary)',  bg: 'var(--surface-input)' },
  waiting:      { label: 'Waiting',    color: 'var(--text-tertiary)',  bg: 'var(--surface-input)' },
  cutting:      { label: 'Cutting',    color: '#38bdf8',               bg: 'rgba(56,189,248,0.12)', pulse: true },
  transcribing: { label: 'Subtitles',  color: '#fbbf24',               bg: 'rgba(251,191,36,0.12)', pulse: true },
  rendering:    { label: 'Rendering',  color: '#a855f7',               bg: 'rgba(168,85,247,0.12)', pulse: true },
  done:         { label: 'Done',       color: '#34C878',               bg: 'rgba(52,200,120,0.1)' },
  failed:       { label: 'Failed',     color: '#E05252',               bg: 'rgba(224,82,82,0.1)' },
  skipped:      { label: 'Skipped',    color: 'var(--text-tertiary)',  bg: 'var(--surface-input)' },
}

const STEP_ICONS: Record<string, string> = {
  waiting: '○', cutting: '✂', transcribing: '♦',
  rendering: '▶', done: '✓', failed: '✕', skipped: '–',
}

function stepStyle(status: string): StepStyle {
  return STEP_STYLES[status] ?? { label: status, color: 'var(--text-tertiary)', bg: 'var(--surface-input)' }
}

// ── Clip list ──────────────────────────────────────────────────────────────────

function ClipList({ parts, totalCount }: { parts: LivePart[]; totalCount: number }) {
  // Build full clip rows: use live data if available, else show placeholder
  const partMap = new Map(parts.map((p) => [p.part_no, p]))
  const rows: LivePart[] = Array.from({ length: Math.max(totalCount, parts.length) }, (_, i) => {
    const no = i + 1
    return partMap.get(no) ?? { part_no: no, status: 'waiting', progress_percent: 0 }
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '0 0 6px 0',
        borderBottom: '1px solid var(--border-subtle)',
        marginBottom: '4px',
      }}>
        <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase' as const }}>
          Clips — {rows.length} total
        </span>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>
          {parts.filter((p) => p.status === 'done').length} done
          {parts.filter((p) => p.status === 'failed').length > 0
            ? ` · ${parts.filter((p) => p.status === 'failed').length} failed` : ''}
        </span>
      </div>

      {rows.map((p) => {
        const ss = stepStyle(p.status)
        const icon = STEP_ICONS[p.status] ?? '○'
        const isActive = ss.pulse
        const isDone = p.status === 'done'

        return (
          <div
            key={p.part_no}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '8px 10px',
              borderRadius: '8px',
              backgroundColor: isActive ? 'rgba(168,85,247,0.03)' : 'transparent',
              border: `1px solid ${isActive ? 'rgba(168,85,247,0.12)' : 'var(--border-subtle)'}`,
              transition: 'all 0.2s ease',
            }}
          >
            {/* Clip number */}
            <span style={{
              fontSize: '10px',
              fontWeight: 700,
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)',
              flexShrink: 0,
              width: '36px',
            }}>
              Clip {p.part_no}
            </span>

            {/* Step progress bar (only for active clips) */}
            {isActive && p.progress_percent > 0 ? (
              <div style={{ flex: 1, height: '3px', backgroundColor: 'var(--surface-input)', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${p.progress_percent}%`,
                  background: 'linear-gradient(90deg, #a855f7, #4d7cff)',
                  borderRadius: '2px',
                  transition: 'width 0.4s ease',
                }} />
              </div>
            ) : (
              <div style={{ flex: 1, height: '3px', backgroundColor: isDone ? 'rgba(52,200,120,0.3)' : 'var(--surface-input)', borderRadius: '2px' }} />
            )}

            {/* Status pill */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: ss.bg,
              flexShrink: 0,
              animation: isActive ? 'mon-pulse 2s ease-in-out infinite' : 'none',
            }}>
              <span style={{ fontSize: '9px', color: ss.color, lineHeight: 1 }}>{icon}</span>
              <span style={{
                fontSize: '10px',
                fontWeight: 700,
                color: ss.color,
                letterSpacing: '0.03em',
              }}>
                {ss.label}
              </span>
            </div>

            {/* Progress percent (active only) */}
            {isActive && p.progress_percent > 0 && (
              <span style={{ fontSize: '10px', color: '#a855f7', fontWeight: 600, flexShrink: 0, width: '30px', textAlign: 'right' as const, fontFamily: 'var(--font-mono)' }}>
                {p.progress_percent}%
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Active job panel ───────────────────────────────────────────────────────────

interface ActivePanelProps {
  item: HistoryItem
  progress: number
  stage: string
  etaSec: number | null
  liveParts: LivePart[]
  wsConnected: boolean
  onCancel: () => void
}

function ActivePanel({ item, progress, stage, etaSec, liveParts, wsConnected, onCancel }: ActivePanelProps) {
  const isDone = item.status === 'completed' || item.status === 'completed_with_errors'
  const isFailed = item.status === 'failed' || item.status === 'cancelled'
  const isRunning = !isDone && !isFailed

  const stageLabel = stage
    ? stage.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : 'Processing…'

  return (
    <div style={{
      margin: 'var(--space-4) var(--space-6)',
      padding: '20px',
      backgroundColor: 'var(--surface-card)',
      border: '1px solid rgba(168,85,247,0.2)',
      borderRadius: '16px',
      boxShadow: '0 0 24px rgba(168,85,247,0.06)',
    }}>
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', gap: '12px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            {isRunning && (
              <span style={{
                display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%',
                backgroundColor: '#a855f7', animation: 'mon-pulse 1.5s ease-in-out infinite',
                flexShrink: 0,
              }} />
            )}
            {isDone && <span style={{ color: '#34C878', fontSize: '14px' }}>✓</span>}
            {isFailed && <span style={{ color: '#E05252', fontSize: '14px' }}>✕</span>}
            <span style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 700,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap' as const,
            }}>
              {(item.title || item.source_hint || 'Untitled').slice(0, 60)}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' as const }}>
            <span style={{
              fontSize: '11px',
              color: isRunning ? '#a855f7' : isDone ? '#34C878' : '#E05252',
              fontWeight: 600,
            }}>
              {isRunning ? stageLabel : isDone ? 'Complete' : 'Failed'}
            </span>
            {isRunning && etaSec !== null && etaSec > 0 && (
              <span style={{
                fontSize: '11px',
                color: 'var(--text-tertiary)',
                padding: '1px 7px',
                backgroundColor: 'var(--surface-input)',
                borderRadius: '10px',
                border: '1px solid var(--border-subtle)',
              }}>
                {formatEta(etaSec)}
              </span>
            )}
            <span style={{
              fontSize: '11px',
              color: 'var(--text-tertiary)',
            }}>
              {item.total_count} clip{item.total_count !== 1 ? 's' : ''}
            </span>
            {/* WS badge */}
            <span style={{
              fontSize: '9px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase' as const,
              color: wsConnected ? '#34C878' : 'var(--text-tertiary)',
              backgroundColor: wsConnected ? 'rgba(52,200,120,0.1)' : 'var(--surface-input)',
              border: `1px solid ${wsConnected ? 'rgba(52,200,120,0.25)' : 'var(--border-subtle)'}`,
              padding: '1px 6px',
              borderRadius: '5px',
            }}>
              {wsConnected ? 'Live' : 'Polling'}
            </span>
          </div>
        </div>
        {isRunning && (
          <button onClick={onCancel} style={{
            height: '30px', padding: '0 12px',
            border: '1px solid var(--border-default)',
            borderRadius: '8px', backgroundColor: 'transparent',
            color: 'var(--text-secondary)', fontSize: '11px', fontWeight: 600,
            cursor: 'pointer', flexShrink: 0,
          }}>
            Cancel
          </button>
        )}
      </div>

      {/* Overall progress bar */}
      {isRunning && (
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', fontWeight: 500 }}>Overall progress</span>
            <span style={{ fontSize: '10px', color: progress > 0 ? '#a855f7' : 'var(--text-tertiary)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
              {progress > 0 ? `${progress}%` : '—'}
            </span>
          </div>
          <div style={{ height: '5px', backgroundColor: 'var(--surface-input)', borderRadius: '3px', overflow: 'hidden' }}>
            {progress > 0 ? (
              <div style={{
                height: '100%', width: `${progress}%`,
                background: 'linear-gradient(90deg, #a855f7, #4d7cff)',
                borderRadius: '3px', transition: 'width 0.5s ease',
              }} />
            ) : (
              <div style={{
                height: '100%', width: '40%',
                background: 'linear-gradient(90deg, #a855f7, #4d7cff)',
                borderRadius: '3px', animation: 'mon-slide 2s ease-in-out infinite',
              }} />
            )}
          </div>
        </div>
      )}

      {/* Pipeline stage track */}
      <PipelineTrack stage={stage} done={isDone} />

      {/* Clip list */}
      <ClipList parts={liveParts} totalCount={item.total_count || 0} />
    </div>
  )
}

// ── History job row (compact) ──────────────────────────────────────────────────

function HistoryRow({ item }: { item: HistoryItem }) {
  const [hovered, setHovered] = useState(false)
  const isCompleted = item.status === 'completed' || item.status === 'completed_with_errors'
  const isFailed = item.status === 'failed' || item.status === 'cancelled'
  const isQueued = item.status === 'queued'

  const statusColor = isCompleted ? '#34C878' : isFailed ? '#E05252' : '#a855f7'
  const statusLabel = isCompleted ? 'Done' : isFailed ? 'Failed' : isQueued ? 'Queued' : 'Running'

  const openFolder = async () => {
    const api = (window as any).electronAPI
    if (api?.openPath && item.output_dir) await api.openPath(item.output_dir)
  }

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 14px',
        borderRadius: '10px',
        backgroundColor: hovered ? 'rgba(255,255,255,0.025)' : 'transparent',
        border: `1px solid ${hovered ? 'var(--border-default)' : 'var(--border-subtle)'}`,
        transition: 'all 0.12s ease',
      }}
    >
      {/* Status indicator */}
      <div style={{
        width: '6px', height: '6px', borderRadius: '50%',
        backgroundColor: statusColor, flexShrink: 0,
        opacity: isQueued ? 0.5 : 1,
      }} />

      {/* Title */}
      <span style={{
        flex: 1, fontSize: '12px', fontWeight: 500,
        color: 'var(--text-secondary)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
      }}>
        {(item.title || item.source_hint || 'Untitled').slice(0, 60)}
      </span>

      {/* Stats */}
      <span style={{ fontSize: '11px', color: statusColor, fontWeight: 600, flexShrink: 0 }}>
        {statusLabel}
      </span>
      {isCompleted && item.completed_count > 0 && (
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', flexShrink: 0 }}>
          {item.completed_count} clip{item.completed_count !== 1 ? 's' : ''}
          {item.failed_count > 0 ? ` · ${item.failed_count} failed` : ''}
        </span>
      )}
      {item.created_at && (
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', flexShrink: 0, fontFamily: 'var(--font-mono)' }}>
          {relativeTime(item.created_at)}
        </span>
      )}

      {/* Open folder */}
      {isCompleted && item.can_open_folder && hovered && (
        <button onClick={openFolder} style={{
          height: '26px', padding: '0 10px', flexShrink: 0,
          border: '1px solid rgba(52,200,120,0.35)',
          borderRadius: '6px', backgroundColor: 'rgba(52,200,120,0.08)',
          color: '#34C878', fontSize: '11px', fontWeight: 600, cursor: 'pointer',
        }}>
          Open
        </button>
      )}
    </div>
  )
}

// ── MonitorStep ────────────────────────────────────────────────────────────────

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

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wsFallbackActiveRef = useRef(false)

  const poll = useCallback(async () => {
    try {
      const res = await getJobHistory(10, 0)
      setItems(res.items)
    } catch { /* ignore */ }
  }, [])

  const startHttpFallback = useCallback(() => {
    if (wsFallbackActiveRef.current) return
    wsFallbackActiveRef.current = true
    poll()
    intervalRef.current = setInterval(poll, 2000)
  }, [poll])

  const stopHttpPoll = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
    wsFallbackActiveRef.current = false
  }, [])

  useEffect(() => {
    if (!jobId) return
    const ws = new WebSocket(`ws://127.0.0.1:8000/api/jobs/${jobId}/ws`)
    wsRef.current = ws
    ws.onopen = () => { setWsConnected(true); stopHttpPoll(); poll() }
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string)
        const summary = data.summary ?? {}
        setProgress(summary.overall_progress_percent ?? data.job?.progress_percent ?? 0)
        setStage(summary.current_stage ?? data.job?.stage ?? '')
        setEtaSec(typeof summary.eta_seconds === 'number' ? summary.eta_seconds : null)
        if (Array.isArray(data.parts)) setLiveParts(data.parts as LivePart[])
        const status: string = summary.status ?? data.job?.status ?? ''
        if (TERMINAL_STATUSES.has(status)) {
          ws.close(); poll()
          if (status === 'completed' || status === 'completed_with_errors') onComplete()
        }
      } catch { /* ignore */ }
    }
    ws.onerror = () => { setWsConnected(false); startHttpFallback() }
    ws.onclose  = () => { setWsConnected(false) }
    return () => ws.close()
  }, [jobId, onComplete, poll, startHttpFallback, stopHttpPoll])

  useEffect(() => {
    poll()
    if (!jobId) { intervalRef.current = setInterval(poll, 2000); return () => { if (intervalRef.current) clearInterval(intervalRef.current) } }
    return () => stopHttpPoll()
  }, [jobId, poll, stopHttpPoll])

  const cancelJob = async () => {
    if (!jobId) return
    try { await fetch(`/api/render/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }) } catch { /* ignore */ }
  }

  const currentItem = jobId ? items.find((i) => i.job_id === jobId) : null
  const historyItems = items.filter((i) => i.job_id !== jobId)

  const filtered = historyItems.filter((item) => {
    if (tab === 'all') return true
    if (tab === 'rendering') return item.status === 'running' || item.status === 'queued'
    if (tab === 'completed') return item.status === 'completed' || item.status === 'completed_with_errors'
    if (tab === 'failed') return item.status === 'failed' || item.status === 'cancelled'
    return true
  })

  const countAll = historyItems.length
  const countRendering = historyItems.filter((i) => i.status === 'running' || i.status === 'queued').length
  const countCompleted = historyItems.filter((i) => i.status === 'completed' || i.status === 'completed_with_errors').length
  const countFailed    = historyItems.filter((i) => i.status === 'failed' || i.status === 'cancelled').length

  const currentJobDone = currentItem
    ? currentItem.status === 'completed' || currentItem.status === 'completed_with_errors'
    : false

  const TABS: Array<{ id: TabFilter; label: string; count: number }> = [
    { id: 'all',       label: 'History',   count: countAll },
    { id: 'rendering', label: 'Running',   count: countRendering },
    { id: 'completed', label: 'Done',      count: countCompleted },
    { id: 'failed',    label: 'Failed',    count: countFailed },
  ]

  return (
    <>
      <style>{`
        @keyframes mon-pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes mon-slide { 0%{transform:translateX(-150%)} 100%{transform:translateX(300%)} }
      `}</style>

      <div style={s.page}>
        {/* ── Active job panel ── */}
        {currentItem && (
          <ActivePanel
            item={currentItem}
            progress={progress}
            stage={stage}
            etaSec={etaSec}
            liveParts={liveParts}
            wsConnected={wsConnected}
            onCancel={cancelJob}
          />
        )}

        {/* ── Complete banner ── */}
        {currentJobDone && (
          <div style={s.successFooter}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#34C878' }}>
              <span style={{ fontSize: '20px' }}>✓</span>
              <div>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>Render Complete</div>
                <div style={{ fontSize: '11px', opacity: 0.7 }}>Your clips are ready</div>
              </div>
            </div>
            <button onClick={onComplete} style={s.viewResultsBtn}>
              {t('monitor_continue')} →
            </button>
          </div>
        )}

        {/* ── History section ── */}
        {historyItems.length > 0 && (
          <>
            {/* Section header + tabs */}
            <div style={s.sectionHeader}>
              <span style={s.sectionTitle}>History</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                {TABS.map((tb) => (
                  <button
                    key={tb.id}
                    onClick={() => setTab(tb.id)}
                    style={{
                      height: '26px',
                      padding: '0 10px',
                      border: '1px solid ' + (tab === tb.id ? 'rgba(168,85,247,0.4)' : 'var(--border-subtle)'),
                      borderRadius: '20px',
                      backgroundColor: tab === tb.id ? 'rgba(168,85,247,0.1)' : 'transparent',
                      color: tab === tb.id ? '#a855f7' : 'var(--text-tertiary)',
                      fontSize: '11px',
                      fontWeight: tab === tb.id ? 700 : 400,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    {tb.label}
                    {tb.count > 0 && (
                      <span style={{
                        fontSize: '9px',
                        fontWeight: 700,
                        color: tab === tb.id ? '#a855f7' : 'var(--text-tertiary)',
                        backgroundColor: tab === tb.id ? 'rgba(168,85,247,0.15)' : 'var(--surface-input)',
                        padding: '0 4px',
                        borderRadius: '6px',
                      }}>
                        {tb.count}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div style={s.historyList}>
              {filtered.length === 0 ? (
                <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', padding: '8px 0' }}>No jobs in this category.</span>
              ) : (
                filtered.map((item) => <HistoryRow key={item.job_id} item={item} />)
              )}
            </div>
          </>
        )}

        {/* Empty state — no current job and no history */}
        {!currentItem && historyItems.length === 0 && (
          <div style={s.empty}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.15, color: 'var(--text-tertiary)' }}>
              <rect x="2" y="2" width="20" height="20" rx="3"/>
              <polygon points="10 8 16 12 10 16 10 8"/>
            </svg>
            <span style={s.emptyText}>No render jobs yet.</span>
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
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-base)',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px var(--space-6) 8px',
    flexShrink: 0,
  },
  sectionTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-tertiary)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  historyList: {
    padding: '0 var(--space-6) var(--space-4)',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
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
    margin: '0 var(--space-6)',
    borderRadius: '12px',
    backgroundColor: 'rgba(52,200,120,0.06)',
    border: '1px solid rgba(52,200,120,0.2)',
    marginBottom: 'var(--space-3)',
  },
  viewResultsBtn: {
    height: '36px',
    padding: '0 18px',
    border: 'none',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
    color: '#fff',
    fontSize: '12px',
    fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 0 12px rgba(168,85,247,0.3)',
  },
}
