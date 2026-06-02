import React, { useState, useRef, useEffect } from 'react'
import type { JobPart, WsProgressSummary } from '@/types/api'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'

function buildClipSlots(liveParts: JobPart[], progress: WsProgressSummary | null): ClipSlot[] {
  if (liveParts.length > 0) {
    return liveParts.map((p) => ({
      part_no: p.part_no,
      status: p.status,
      progress_percent: p.progress_percent ?? 0,
      duration: p.duration,
      message: p.message,
    }))
  }
  if (!progress) return []
  const slots: ClipSlot[] = []
  const active = Array.isArray(progress.active_parts) ? progress.active_parts : []
  let no = 1
  for (let i = 0; i < progress.completed_parts; i++) slots.push({ part_no: no++, status: 'done', progress_percent: 100 })
  active.forEach((a) => slots.push({ part_no: a.part_no, status: a.status, progress_percent: a.progress_percent }))
  for (let i = 0; i < progress.failed_parts; i++) slots.push({ part_no: no++, status: 'failed', progress_percent: 0 })
  for (let i = 0; i < progress.pending_parts; i++) slots.push({ part_no: no++, status: 'waiting', progress_percent: 0 })
  return slots
}

function getActivePhaseIdx(stage: string, jobStatus: string): number {
  const s = (stage || jobStatus).toLowerCase()
  if (s === 'done') return 4
  if (s.includes('render') || s.includes('writing')) return 3
  if (s.includes('transcrib')) return 2
  if (s.includes('scene') || s.includes('segment')) return 1
  if (s.includes('download')) return 0
  return -1
}

export function clipStateKey(status: string): 'done' | 'failed' | 'active' | 'waiting' {
  const s = status.toLowerCase()
  if (s === 'done') return 'done'
  if (s === 'failed' || s === 'cancelled') return 'failed'
  if (s === 'waiting' || s === 'queued') return 'waiting'
  return 'active'
}

const ACTIVITY_LABELS: Record<string, string> = {
  cutting:      'Extracting video segment · FFmpeg',
  transcribing: 'Generating subtitles · Whisper AI',
  rendering:    'Encoding clip · FFmpeg NVENC',
}

const STEP_NODES = [
  { key: 'cutting',      label: 'Cut' },
  { key: 'transcribing', label: 'Sub' },
  { key: 'rendering',    label: 'Render' },
]

function ClipRow({ slot, statusLabel, jobId, thumbRatio, compact = false }: {
  slot: ClipSlot; statusLabel: string; jobId: string | null; thumbRatio: string; compact?: boolean
}) {
  const state   = clipStateKey(slot.status)
  const pct     = slot.progress_percent
  const isDone  = state === 'done'
  const isFail  = state === 'failed'
  const isWait  = state === 'waiting'
  const isActive = state === 'active'
  const activity = ACTIVITY_LABELS[slot.status.toLowerCase()] ?? ''
  const activeStepIdx = STEP_NODES.findIndex((n) => n.key === slot.status.toLowerCase())

  const thumbUrl = jobId ? getPartThumbnailUrl(jobId, slot.part_no) : null

  // Audit followup_4: status color map sourced from design tokens so
  // theme drift can't fork into per-file palettes. Status-success/
  // ai-active map to the semantic intent. Waiting/error use rgb(107,114,128)
  // and rgb(239,68,68) — those have no exact token at present; tracked.
  const ACCENT: Record<string, string> = {
    done:    'var(--status-success)',
    failed:  '#ef4444',
    active:  'var(--ai-active)',
    waiting: '#6b7280',
  }
  const accentColor = ACCENT[state] ?? '#6b7280'

  if (compact) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '5px 10px', borderRadius: 7,
        background: isDone ? 'rgba(52,200,120,.04)' : 'transparent',
        border: `1px solid ${isDone ? 'rgba(52,200,120,.1)' : 'rgba(255,255,255,.04)'}`,
      }}>
        <span style={{ fontSize: 13, color: accentColor, flexShrink: 0, width: 14, textAlign: 'center', lineHeight: 1 }}>
          {isDone ? '✓' : '○'}
        </span>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', fontFamily: 'monospace', flexShrink: 0 }}>
          #{String(slot.part_no).padStart(2, '0')}
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-3)', flex: 1 }}>{statusLabel}</span>
        {slot.duration != null && slot.duration > 0 && (
          <span style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--text-3)', flexShrink: 0 }}>
            {Math.floor(slot.duration / 60)}:{String(Math.floor(slot.duration % 60)).padStart(2, '0')}
          </span>
        )}
        {isDone && jobId && (
          <a href={getPartMediaUrl(jobId, slot.part_no)} target="_blank" rel="noreferrer"
            style={{ fontSize: 9, color: 'var(--status-success)', textDecoration: 'none', fontWeight: 700, letterSpacing: '.04em', flexShrink: 0 }}>
            ▶
          </a>
        )}
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex',
      borderRadius: 10,
      overflow: 'hidden',
      background: 'var(--bg-card)',
      border: `1px solid ${isActive ? 'rgba(168,85,247,.25)' : 'var(--border)'}`,
      boxShadow: isActive ? '0 0 10px rgba(168,85,247,.08)' : 'none',
      transition: 'border-color .15s',
    }}>
      {/* Left accent bar */}
      <div style={{ width: 3, flexShrink: 0, background: `linear-gradient(180deg,${accentColor},${accentColor}55)` }} />

      {/* Thumbnail */}
      <div style={{
        width: 52, flexShrink: 0,
        aspectRatio: thumbRatio,
        background: 'rgba(255,255,255,.04)',
        overflow: 'hidden', position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {thumbUrl && isDone ? (
          <img
            src={thumbUrl}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <span style={{ fontSize: 16, opacity: .25 }}>
            {isFail ? '✕' : isWait ? '○' : isActive ? '▶' : '✓'}
          </span>
        )}
        {isActive && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 3,
            background: 'rgba(255,255,255,.08)',
          }}>
            <div style={{
              height: '100%',
              width: `${pct}%`,
              background: `linear-gradient(90deg,${accentColor},var(--accent-primary))`,
              transition: 'width .4s ease',
            }} />
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '8px 12px', minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: isActive ? 6 : 0 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', fontFamily: 'monospace', flexShrink: 0 }}>
            #{String(slot.part_no).padStart(2, '0')}
            {slot.duration != null && slot.duration > 0 && (
              <span style={{ fontWeight: 400, opacity: 0.55, marginLeft: 4 }}>
                {Math.floor(slot.duration / 60)}:{String(Math.floor(slot.duration % 60)).padStart(2, '0')}
              </span>
            )}
          </span>

          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20, flexShrink: 0,
            background: `${accentColor}20`, color: accentColor,
            animation: isActive ? 'rndv-badge-pulse 1.4s ease-in-out infinite' : 'none',
          }}>
            {isActive && <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: accentColor, marginRight: 4, verticalAlign: 'middle' }} />}
            {statusLabel}
          </span>

          <div style={{ flex: 1, height: 3, borderRadius: 99, background: 'rgba(255,255,255,.07)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 99,
              width: `${isDone ? 100 : isFail || isWait ? 0 : pct}%`,
              background: isDone
                ? 'linear-gradient(90deg,var(--status-success),#22c55e)'
                : `linear-gradient(90deg,${accentColor},var(--accent-primary))`,
              transition: 'width .4s ease',
            }} />
          </div>

          <span style={{ fontSize: 10, fontWeight: 700, fontFamily: 'monospace', flexShrink: 0, color: accentColor }}>
            {isDone ? '100%' : isFail ? 'ERR' : isWait ? '—' : `${pct}%`}
          </span>
        </div>

        {isActive && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {STEP_NODES.map((n, i) => {
                const st = i < activeStepIdx ? 'done' : i === activeStepIdx ? 'active' : 'pending'
                const col = st === 'done' ? 'var(--status-success)' : st === 'active' ? 'var(--ai-active)' : '#6b7280'
                return (
                  <React.Fragment key={n.key}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <div style={{
                        width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
                        border: `2px solid ${col}`,
                        background: st === 'done' ? col : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 7,
                      }}>
                        {st === 'done' && <span style={{ color: '#000' }}>✓</span>}
                        {st === 'active' && <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: col, animation: 'rndv-badge-pulse 1.2s ease-in-out infinite' }} />}
                      </div>
                      <span style={{ fontSize: 9, color: col, fontWeight: st === 'active' ? 700 : 500 }}>{n.label}</span>
                    </div>
                    {i < STEP_NODES.length - 1 && (
                      <div style={{ flex: 1, height: 1, background: i < activeStepIdx ? 'var(--status-success)' : 'rgba(255,255,255,.1)', maxWidth: 20 }} />
                    )}
                  </React.Fragment>
                )
              })}
            </div>
            {(slot.message || activity) && (
              <div style={{ fontSize: 9, color: 'var(--text-3)', paddingLeft: 2 }}>
                {slot.message || activity}
              </div>
            )}
          </div>
        )}
        {isFail && slot.message && (
          <div style={{ fontSize: 9, color: 'var(--fail)', opacity: 0.8, paddingLeft: 2, marginTop: 4, lineHeight: 1.4 }}>
            {slot.message}
          </div>
        )}
        {isDone && jobId && (
          <div style={{ marginTop: 4 }}>
            <a
              href={getPartMediaUrl(jobId, slot.part_no)}
              target="_blank" rel="noreferrer"
              style={{ fontSize: 9, color: 'var(--status-success)', textDecoration: 'none', fontWeight: 700, letterSpacing: '.04em' }}
            >
              ▶ PREVIEW
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

// Sprint 5.7: wrapped in React.memo at export below. See StepConfigure for rationale.
function StepRenderingBase({
  jobId, stage, jobStatus, progress, jobMessage, isTerminal, liveParts, wsError, wsReconnecting, t, aspectRatio,
  aiAnalysisMode, aiCloudProvider,
}: {
  jobId: string | null; stage: string; jobStatus: string
  progress: WsProgressSummary | null; jobMessage: string
  isTerminal: boolean; liveParts: JobPart[]
  wsError: string | null; wsReconnecting?: boolean; t: Strings; aspectRatio: string
  aiAnalysisMode?: string; aiCloudProvider?: string
}) {
  const pct         = progress?.overall_progress_percent ?? 0
  const doneCount   = progress?.completed_parts ?? 0
  const totalCount  = progress?.total_parts ?? liveParts.length
  const failedCount = progress?.failed_parts ?? 0

  const startRef = useRef<number>(Date.now())
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (isTerminal) return
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)
    return () => clearInterval(id)
  }, [isTerminal])
  const mm = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const ss = (elapsed % 60).toString().padStart(2, '0')

  const etaSec = pct > 2 && !isTerminal ? Math.round(elapsed * (100 - pct) / pct) : null
  const etaMm  = etaSec !== null ? Math.floor(etaSec / 60).toString().padStart(2, '0') : null
  const etaSs  = etaSec !== null ? (etaSec % 60).toString().padStart(2, '0') : null

  const phases = [
    { key: 'download',   label: t.rndPhaseDownload },
    { key: 'analyze',    label: t.rndPhaseAnalyze },
    { key: 'transcribe', label: t.rndPhaseTranscribe },
    { key: 'render',     label: t.rndPhaseRender },
    { key: 'done',       label: t.rndPhaseDone },
  ]
  const activePhaseIdx = getActivePhaseIdx(stage, jobStatus)
  const clipSlots      = buildClipSlots(liveParts, progress)
  const thumbRatio     = aspectRatio.replace(':', '/')

  function getStatusLabel(s: string): string {
    const sl = s.toLowerCase()
    if (sl === 'done') return t.rndStatusDone
    if (sl === 'rendering') return t.rndStatusRendering
    if (sl === 'cutting') return t.rndStatusCutting
    if (sl === 'transcribing') return t.rndStatusTranscribing
    if (sl === 'failed' || sl === 'cancelled') return t.rndStatusFailed
    return t.rndStatusWaiting
  }

  const isFailed   = jobStatus?.toLowerCase().includes('fail') || jobStatus?.toLowerCase() === 'cancelled'
  const displayMsg = jobMessage
    || (isTerminal ? (isFailed ? '✕ ' + t.rndStatusFailed : '✓ ' + t.rndComplete) : t.rndPreparing)

  void phases

  return (
    <div className="rnd-screen">

      <div className="rd-card">
        <div className="rd-card-head">
          <div className="rd-head-left">
            <span className={`rd-status-badge rd-status-${isFailed ? 'failed' : isTerminal ? 'done' : 'running'}`}>
              {isFailed ? 'FAILED' : isTerminal ? 'DONE' : 'RENDERING'}
            </span>
            <span className="rd-card-title">
              {isFailed ? t.rndFailed : isTerminal ? t.rndComplete : t.rndInProgress}
            </span>
          </div>
          {!isTerminal && jobId && (
            <span className="rd-elapsed">
              {mm}:{ss}
              {etaMm !== null && (
                <span style={{ opacity: 0.5, marginLeft: 6, fontWeight: 400 }}>ETA {etaMm}:{etaSs}</span>
              )}
            </span>
          )}
        </div>

        <div className="rd-step-text">
          {activePhaseIdx >= 0 && phases[activePhaseIdx]
            ? `${phases[activePhaseIdx].label}${displayMsg ? ' — ' + displayMsg : ''}`
            : displayMsg}
        </div>

        {clipSlots.length > 0 && (
          <div className="rd-seg-bar">
            {clipSlots.map(slot => (
              <div key={slot.part_no} className={`rd-seg rd-seg-${clipStateKey(slot.status)}`}
                title={`Clip ${slot.part_no}: ${slot.status}`} />
            ))}
          </div>
        )}

        <div className="rd-overall">
          <span className="rd-overall-pct">
            {Math.round(pct)}%
            {!isTerminal && pct > 0 && pct < 100 && (
              <span style={{ fontSize: '0.65em', opacity: 0.45, marginLeft: 4, fontWeight: 400 }}>est.</span>
            )}
          </span>
          <div className="rd-overall-right">
            {totalCount > 0 && (
              <span className="rd-clips-text">
                {t.rndClipsDone(doneCount, totalCount)}
                {failedCount > 0 && <span style={{ color: 'var(--fail)' }}> · {t.rndClipsFailed(failedCount)}</span>}
              </span>
            )}
            <div className="rd-bar-track">
              <div className="rd-bar-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>
      </div>

      {aiAnalysisMode && (
        <div className="rd-ai-panel">
          <div className="rd-ai-head">
            <span className="rd-ai-label">AI Director</span>
            <span className={`rd-ai-mode-badge rd-ai-${aiAnalysisMode}`}>
              {aiAnalysisMode === 'hybrid' ? '⚡ Hybrid' : aiAnalysisMode === 'cloud' ? '☁ Cloud' : '💻 Local'}
            </span>
            {aiAnalysisMode !== 'local' && aiCloudProvider && (
              <span className="rd-ai-provider">{aiCloudProvider === 'groq' ? 'Groq' : 'OpenAI'}</span>
            )}
          </div>
          <div className="rd-ai-body">
            {stage === 'analyze' && !isTerminal
              ? <><span className="rd-ai-pulse" /> AI Director analyzing content — selecting best moments…</>
              : stage === 'transcribe' && !isTerminal
              ? 'Transcribing audio — Whisper AI processing…'
              : stage === 'render' && !isTerminal && totalCount > 0
              ? `Rendering ${totalCount} clip${totalCount !== 1 ? 's' : ''} — AI scene tracking active`
              : isTerminal && !isFailed
              ? `Analysis complete — ${doneCount} clip${doneCount !== 1 ? 's' : ''} selected`
              : displayMsg || 'Processing…'
            }
          </div>
        </div>
      )}

      {!isTerminal && (wsReconnecting || wsError) && (
        <div style={{ padding: '8px 16px', background: 'rgba(234,179,8,.1)', borderBottom: '1px solid rgba(234,179,8,.2)', fontSize: '11px', color: 'var(--warn)', flexShrink: 0 }}>
          {wsReconnecting ? `↻ ${t.rndWsReconnecting}` : `⚠ ${t.rndWsError}`}
        </div>
      )}

      {clipSlots.length === 0 ? (
        <div className="rnd-waiting-msg">
          <span className="rnd-waiting-dot" />
          <span>
            {t.rndPreparing}
            {jobMessage && <span style={{ display: 'block', fontSize: '10px', opacity: .55, marginTop: 2 }}>{jobMessage}</span>}
          </span>
        </div>
      ) : (
        <div className="rd-queue-scroll" style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 12px' }}>
          {clipSlots.map(slot => (
            <ClipRow
              key={slot.part_no}
              slot={slot}
              statusLabel={getStatusLabel(slot.status)}
              jobId={jobId}
              thumbRatio={thumbRatio}
              compact={clipStateKey(slot.status) === 'done' || clipStateKey(slot.status) === 'waiting'}
            />
          ))}
        </div>
      )}

      <div className="rd-abp-toolbar">
        <div className="rd-abp-job">
          <div className="rd-abp-title">{jobId ? jobId.slice(-12) : '—'}</div>
          <div className="rd-abp-meta">{totalCount > 0 ? `${totalCount} clips · ${aspectRatio}` : aspectRatio}</div>
        </div>
        <div className="rd-abp-progress">
          <div className="rd-abp-bar-track">
            <div className="rd-abp-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="rd-abp-msg">{displayMsg}</div>
        </div>
        <span className="rd-abp-pct">{Math.round(pct)}%</span>
        <span className={`rd-abp-badge rd-status-${isFailed ? 'failed' : isTerminal ? 'done' : 'running'}`}>
          {isFailed ? 'FAILED' : isTerminal ? 'DONE' : 'RUNNING'}
        </span>
      </div>

    </div>
  )
}

export const StepRendering = React.memo(StepRenderingBase)
