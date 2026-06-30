import React, { useState, useRef, useEffect, useMemo } from 'react'
import type { JobPart, WsProgressSummary } from '@/types/api'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import type { WsLogEvent } from '@/websocket/events'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { estimateRenderEtaSec } from '../eta'
import { stageBlendedPercent } from '../progress'
import { RecapLiveView } from './RecapLiveView'
import { extendJob } from '@/api/jobs'
import type { JobPartStageEnum } from '@/types/enums'

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
] as const satisfies readonly { key: JobPartStageEnum; label: string }[]

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

  // S4.1 — per-clip ETA. Track when the clip first transitioned into an
  // active state so the heuristic uses *this clip's* elapsed time
  // rather than the whole job's elapsed time. Reset whenever the clip
  // goes back to waiting or reaches a terminal state.
  const clipStartRef = useRef<number | null>(null)
  useEffect(() => {
    if (isActive) {
      if (clipStartRef.current === null) clipStartRef.current = Date.now()
    } else {
      clipStartRef.current = null
    }
  }, [isActive])
  const clipEtaSec = (() => {
    if (!isActive || clipStartRef.current === null) return null
    if (pct <= 5 || pct >= 100) return null
    const clipElapsed = Math.max(0, (Date.now() - clipStartRef.current) / 1000)
    if (clipElapsed < 3) return null
    const remaining = Math.round(clipElapsed * (100 - pct) / pct)
    if (remaining < 1 || remaining > 60 * 60) return null
    return remaining
  })()
  const clipEtaLabel = clipEtaSec !== null
    ? clipEtaSec < 60
      ? `${clipEtaSec}s`
      : `${Math.floor(clipEtaSec / 60)}:${String(clipEtaSec % 60).padStart(2, '0')}`
    : null

  const thumbUrl = jobId ? getPartThumbnailUrl(jobId, slot.part_no) : null

  // Audit followup_4: status color map sourced from design tokens so
  // theme drift can't fork into per-file palettes. Status-success/
  // ai-active map to the semantic intent. Waiting/error use rgb(107,114,128)
  // and rgb(239,68,68) — those have no exact token at present; tracked.
  const ACCENT: Record<string, string> = {
    done:    'var(--status-success)',
    failed:  'var(--color-error)',
    active:  'var(--ai-active)',
    waiting: 'var(--status-waiting)',
  }
  const accentColor = ACCENT[state] ?? 'var(--status-waiting)'

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
                ? 'linear-gradient(90deg,var(--status-success),var(--color-success))'
                : `linear-gradient(90deg,${accentColor},var(--accent-primary))`,
              transition: 'width .4s ease',
            }} />
          </div>

          <span style={{ fontSize: 10, fontWeight: 700, fontFamily: 'monospace', flexShrink: 0, color: accentColor }}>
            {isDone ? '100%' : isFail ? 'ERR' : isWait ? '—' : `${pct}%`}
          </span>
          {clipEtaLabel && (
            <span style={{
              fontSize: 9, fontWeight: 600, fontFamily: 'monospace', flexShrink: 0,
              color: 'var(--text-3)', opacity: 0.7,
            }} title="Estimated time remaining for this clip">
              ~{clipEtaLabel}
            </span>
          )}
        </div>

        {isActive && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {STEP_NODES.map((n, i) => {
                const st = i < activeStepIdx ? 'done' : i === activeStepIdx ? 'active' : 'pending'
                const col = st === 'done' ? 'var(--status-success)' : st === 'active' ? 'var(--ai-active)' : 'var(--status-waiting)'
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
  jobId, stage, jobStatus, progress, jobMessage, isTerminal, liveParts, liveEvents, recapPlan, wsError, wsReconnecting, wsPolling, t, aspectRatio,
  aiAnalysisMode, aiCloudProvider,
}: {
  jobId: string | null; stage: string; jobStatus: string
  progress: WsProgressSummary | null; jobMessage: string
  isTerminal: boolean; liveParts: JobPart[]
  /** S4.5 — bridged event stream from backend `_emit_render_event`.
   *  Optional so older mount sites without the wiring still compile. */
  liveEvents?: WsLogEvent[]
  /** Latched recap.plan.ready event — stable for the whole render (survives the
   *  bounded liveEvents buffer). Drives recap-mode detection + the timeline. */
  recapPlan?: WsLogEvent | null
  wsError: string | null
  wsReconnecting?: boolean
  // N5 (2026-06-15): true while the WebSocket has exhausted its reconnect
  // budget and the hook is falling back to 5 s HTTP polling. UI was
  // silently swallowing this state — user saw no difference, just
  // slower-than-usual progress updates.
  wsPolling?: boolean
  t: Strings; aspectRatio: string
  aiAnalysisMode?: string; aiCloudProvider?: string
}) {
  const pct         = progress?.overall_progress_percent ?? 0
  // Pha 5.6 — smoother display bar: blend the job stage with the raw parts
  // percent so the bar moves through the pre-render phases instead of sitting
  // at 0 then jumping. `pct` (raw) is still used for the ETA math.
  const displayPct  = stageBlendedPercent(stage || jobStatus, pct)
  const doneCount   = progress?.completed_parts ?? 0
  const totalCount  = progress?.total_parts ?? liveParts.length
  const failedCount = progress?.failed_parts ?? 0
  // S4.3 — backend already computes stuck_parts (>120 s no DB update)
  // in WsProgressSummary; FE was dropping the signal on the floor.
  // Surface it as a banner so a user staring at a frozen progress bar
  // can tell "is this normal slow or actually stuck?" without leaving
  // the screen. Polling-fallback derives an empty list (no per-tick
  // timestamp tracking), which is fine — banner just doesn't appear.
  const stuckParts = progress?.stuck_parts ?? []
  const longestStuckSec = stuckParts.reduce(
    (max, p) => Math.max(max, p.stuck_seconds || 0),
    0,
  )

  const startRef = useRef<number>(Date.now())
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (isTerminal) return
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)
    return () => clearInterval(id)
  }, [isTerminal])
  const mm = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const ss = (elapsed % 60).toString().padStart(2, '0')

  // Pha 5.2 — record the wall-clock gap each time a clip finishes, so the ETA
  // can project from real clip throughput instead of a stage-blind linear
  // extrapolation. Refs (not state) — purely an input to the estimate.
  const clipIntervalsRef = useRef<number[]>([])
  const lastDoneAtRef = useRef<number | null>(null)
  const prevDoneCountRef = useRef(0)
  useEffect(() => {
    if (doneCount > prevDoneCountRef.current) {
      const now = Date.now()
      if (lastDoneAtRef.current !== null) clipIntervalsRef.current.push(now - lastDoneAtRef.current)
      lastDoneAtRef.current = now
      prevDoneCountRef.current = doneCount
    }
  }, [doneCount])

  const etaRaw = isTerminal
    ? null
    : estimateRenderEtaSec({
        elapsedSec: elapsed,
        overallPct: pct,
        doneCount,
        totalCount,
        clipIntervalsMs: clipIntervalsRef.current,
      })
  // Clamp out implausible values (negative / > 6 h) so a noisy early estimate
  // doesn't show a wild number.
  const etaSec = etaRaw !== null && etaRaw > 0 && etaRaw <= 6 * 3600 ? etaRaw : null
  const etaMm  = etaSec !== null ? Math.floor(etaSec / 60).toString().padStart(2, '0') : null
  const etaSs  = etaSec !== null ? (etaSec % 60).toString().padStart(2, '0') : null
  // S4.1 — before the heuristic stabilises (< 2% progress), show an
  // explicit "estimating…" hint instead of leaving the slot blank. The
  // user expects an ETA from second 1 of a 30-minute render; an empty
  // gap reads as "broken", not "still warming up".
  const etaShowEstimating = !isTerminal && jobId !== null && etaSec === null && elapsed > 3

  // S4.4 — watchdog advisory. The backend auto-cancels at 2 h
  // (MAX_JOB_AGE_SECONDS). We warn the user at 90 min so they can
  // grant an extension via POST /api/jobs/{id}/extend. ackedExtendRef
  // remembers whether the user already extended this elapsed window so
  // we don't re-trigger the dialog every render.
  const WATCHDOG_WARN_SEC = 90 * 60  // 90 min
  const showWatchdogAdvisory =
    !isTerminal && jobId !== null && elapsed >= WATCHDOG_WARN_SEC
  const [watchdogDismissed, setWatchdogDismissed] = useState(false)
  const [watchdogExtending, setWatchdogExtending] = useState(false)

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
  // Recap mode: once the plan is ready, the per-part "clip pile" (a clips-mode
  // visual) is misleading — scenes aren't deliverable clips. Show ONLY the
  // recap live-build view instead, so the screen isn't two stacked timelines.
  // Recap detection uses the LATCHED plan event (survives the whole render),
  // not the bounded liveEvents buffer — otherwise the plan ages out after
  // LIVE_EVENTS_CAP events and the view flips back to the clips pile mid-render.
  const isRecap = !!recapPlan
  // Recap counts differ from clips: N internal scenes ("parts") get assembled
  // into a few EPISODES (the real deliverables). Pull the authoritative scene +
  // episode counts from the plan so the chrome stops saying "N clips".
  const recapScenes = (recapPlan?.context?.scenes as unknown[] | undefined)?.length ?? 0
  const recapEpisodes = (recapPlan?.context?.episodes as unknown[] | undefined)?.length ?? 0
  const effTotal = isRecap && recapScenes > 0 ? recapScenes : totalCount

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
              {etaMm !== null ? (
                <span style={{ opacity: 0.5, marginLeft: 6, fontWeight: 400 }}>ETA {etaMm}:{etaSs}</span>
              ) : etaShowEstimating ? (
                <span style={{ opacity: 0.45, marginLeft: 6, fontWeight: 400, fontStyle: 'italic' }}>
                  {t.rndEtaEstimating}
                </span>
              ) : null}
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
            {Math.round(displayPct)}%
            {!isTerminal && displayPct > 0 && displayPct < 100 && (
              <span style={{ fontSize: '0.65em', opacity: 0.45, marginLeft: 4, fontWeight: 400 }}>est.</span>
            )}
          </span>
          <div className="rd-overall-right">
            {effTotal > 0 && (
              <span className="rd-clips-text">
                {isRecap
                  ? `${doneCount} / ${effTotal} cảnh${recapEpisodes > 0 ? ` · ${recapEpisodes} tập` : ''}`
                  : t.rndClipsDone(doneCount, totalCount)}
                {failedCount > 0 && <span style={{ color: 'var(--fail)' }}> · {t.rndClipsFailed(failedCount)}</span>}
              </span>
            )}
            <div className="rd-bar-track">
              <div className="rd-bar-fill" style={{ width: `${displayPct}%` }} />
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
              <span className="rd-ai-provider">{aiCloudProvider === 'openai' ? 'OpenAI' : aiCloudProvider === 'claude' ? 'Claude' : 'Gemini'}</span>
            )}
          </div>
          <div className="rd-ai-body">
            {stage === 'analyze' && !isTerminal
              ? <><span className="rd-ai-pulse" /> AI Director analyzing content — selecting best moments…</>
              : stage === 'transcribe' && !isTerminal
              ? 'Transcribing audio — Whisper AI processing…'
              : stage === 'render' && !isTerminal && isRecap && effTotal > 0
              ? `Dựng ${effTotal} cảnh → ${recapEpisodes || 1} tập — recap đang chạy`
              : stage === 'render' && !isTerminal && totalCount > 0
              ? `Rendering ${totalCount} clip${totalCount !== 1 ? 's' : ''} — AI scene tracking active`
              : isTerminal && !isFailed && isRecap
              ? `Recap xong — ${recapEpisodes || 1} tập`
              : isTerminal && !isFailed
              ? `Analysis complete — ${doneCount} clip${doneCount !== 1 ? 's' : ''} selected`
              : displayMsg || 'Processing…'
            }
          </div>
        </div>
      )}

      {/* Pha 1.3 — single adaptive status line. The four previously-
          stacked advisories (cancelling / stuck / watchdog / WS) answered
          the same user question ("is this fine, slow, stuck, or
          disconnected?") and could pile up three-high. Now exactly one
          shows, by severity priority:
            cancelling > stuck > watchdog > ws-error > ws-reconnecting > ws-polling
          Behaviour + copy are unchanged; the watchdog +1h / dismiss
          actions are preserved inline. */}
      {(() => {
        if (isTerminal) return null
        type StatusKind = 'cancelling' | 'stuck' | 'watchdog' | 'ws-error' | 'ws-reconnecting' | 'ws-polling'
        let kind: StatusKind | null = null
        if (jobStatus === 'cancelling') kind = 'cancelling'
        else if (stuckParts.length > 0) kind = 'stuck'
        else if (showWatchdogAdvisory && !watchdogDismissed) kind = 'watchdog'
        else if (wsError) kind = 'ws-error'
        else if (wsReconnecting) kind = 'ws-reconnecting'
        else if (wsPolling) kind = 'ws-polling'
        if (!kind) return null

        // ws-polling is informational (render unaffected) → accent tone;
        // every other status is an attention/warning → warn tone.
        const isPolling = kind === 'ws-polling'
        return (
          <div style={{
            padding: '9px 16px',
            background: isPolling ? 'rgba(var(--accent-rgb),.08)' : 'rgba(234,179,8,.12)',
            borderBottom: `1px solid ${isPolling ? 'rgba(var(--accent-rgb),.20)' : 'rgba(234,179,8,.25)'}`,
            fontSize: 11,
            color: isPolling ? 'var(--accent)' : 'var(--warn)',
            flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          }}>
            {kind === 'cancelling' && <span>{`◐ ${t.rndCancelling}`}</span>}
            {kind === 'ws-error' && <span>{`⚠ ${t.rndWsError}`}</span>}
            {kind === 'ws-reconnecting' && <span>{`↻ ${t.rndWsReconnecting}`}</span>}
            {kind === 'ws-polling' && <span>{`● ${t.rndWsPolling}`}</span>}

            {kind === 'stuck' && (
              <>
                <span>⚠</span>
                <span style={{ fontWeight: 600 }}>
                  {stuckParts.length === 1
                    ? t.rndStuckOne(stuckParts[0].part_no)
                    : t.rndStuckMany(stuckParts.length)}
                </span>
                <span style={{ opacity: 0.7 }}>
                  {t.rndStuckNoUpdate(Math.round(longestStuckSec))}
                </span>
                <span style={{ flex: 1 }} />
                <span style={{ opacity: 0.6, fontSize: 10 }}>{t.rndStuckHint}</span>
              </>
            )}

            {kind === 'watchdog' && (
              <>
                <span style={{ fontSize: 14 }}>⏰</span>
                <span style={{ fontWeight: 600 }}>{t.rndWatchdogElapsed(Math.floor(elapsed / 60))}</span>
                <span style={{ opacity: 0.8 }}>{t.rndWatchdogWarn}</span>
                <span style={{ flex: 1 }} />
                <button
                  disabled={watchdogExtending}
                  onClick={async () => {
                    if (!jobId) return
                    setWatchdogExtending(true)
                    try {
                      await extendJob(jobId, 3600)
                      setWatchdogDismissed(true)
                    } catch {
                      // 404 = job no longer active (just finished/cancelled)
                      // — dismiss banner silently in that case.
                      setWatchdogDismissed(true)
                    } finally {
                      setWatchdogExtending(false)
                    }
                  }}
                  style={{
                    padding: '4px 12px', borderRadius: 6,
                    fontSize: 10, fontWeight: 700, letterSpacing: '.04em',
                    border: '1px solid var(--warn)',
                    background: 'var(--warn)',
                    color: '#000',
                    cursor: watchdogExtending ? 'not-allowed' : 'pointer',
                    opacity: watchdogExtending ? 0.5 : 1,
                  }}
                >
                  {watchdogExtending ? t.rndWatchdogExtending : '+1h'}
                </button>
                <button
                  onClick={() => setWatchdogDismissed(true)}
                  style={{
                    padding: '4px 10px', borderRadius: 6,
                    fontSize: 10, fontWeight: 600,
                    border: '1px solid var(--border)', background: 'transparent',
                    color: 'var(--text-2)', cursor: 'pointer',
                  }}
                >
                  {t.rndWatchdogDismiss}
                </button>
              </>
            )}
          </div>
        )
      })()}

      {clipSlots.length === 0 ? (
        <div className="rnd-waiting-msg">
          <span className="rnd-waiting-dot" />
          <span>
            {t.rndPreparing}
            {jobMessage && <span style={{ display: 'block', fontSize: '10px', opacity: .55, marginTop: 2 }}>{jobMessage}</span>}
          </span>
        </div>
      ) : isRecap ? null : (
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

      {/* R5 — recap live-build view (renders only when a recap.plan.ready event
          has arrived; null otherwise so clips mode is unaffected). */}
      <RecapLiveView recapPlan={recapPlan ?? null} liveEvents={liveEvents || []} liveParts={liveParts} />

      {/* S4.5 — event log tail panel */}
      <EventLogPanel events={liveEvents || []} t={t} />

      <div className="rd-abp-toolbar">
        <div className="rd-abp-job">
          <div className="rd-abp-title">{jobId ? jobId.slice(-12) : '—'}</div>
          <div className="rd-abp-meta">{isRecap && effTotal > 0 ? `${effTotal} cảnh · ${recapEpisodes || 1} tập · ${aspectRatio}` : totalCount > 0 ? `${totalCount} clips · ${aspectRatio}` : aspectRatio}</div>
        </div>
        <div className="rd-abp-progress">
          <div className="rd-abp-bar-track">
            <div className="rd-abp-bar-fill" style={{ width: `${displayPct}%` }} />
          </div>
          <div className="rd-abp-msg">{displayMsg}</div>
        </div>
        <span className="rd-abp-pct">{Math.round(displayPct)}%</span>
        <span className={`rd-abp-badge rd-status-${isFailed ? 'failed' : isTerminal ? 'done' : 'running'}`}>
          {isFailed ? 'FAILED' : isTerminal ? 'DONE' : 'RUNNING'}
        </span>
      </div>

    </div>
  )
}

export const StepRendering = React.memo(StepRenderingBase)

// ── S4.5 — Event log tail panel ────────────────────────────────────────
//
// Collapsible drawer above the bottom toolbar that surfaces the
// structured event stream backend already emits via _emit_render_event.
// Power-user surface — copy-to-clipboard per event + filter by level
// (warn/error) so a stuck render is debuggable without leaving the UI.

const EVENT_LEVEL_COLORS: Record<string, string> = {
  ERROR:    'var(--fail, #f87171)',
  CRITICAL: 'var(--fail, #f87171)',
  FATAL:    'var(--fail, #f87171)',
  WARN:     'var(--warn, #eab308)',
  WARNING:  'var(--warn, #eab308)',
  INFO:     'var(--text-2)',
  DEBUG:    'var(--text-3)',
}

function EventLogPanel({ events, t }: { events: WsLogEvent[]; t: Strings }) {
  const [open, setOpen] = useState(false)
  const [filterErrors, setFilterErrors] = useState(false)

  const visible = useMemo(() => {
    const list = filterErrors
      ? events.filter((e) => {
        const l = (e.level || '').toUpperCase()
        return l === 'ERROR' || l === 'CRITICAL' || l === 'FATAL' || l === 'WARN' || l === 'WARNING'
      })
      : events
    // Newest at bottom for a tail-like feel; events stream in newest-first
    // from the hook so reverse here.
    return [...list].reverse()
  }, [events, filterErrors])

  function copyEvent(ev: WsLogEvent) {
    const payload = JSON.stringify(ev, null, 2)
    try {
      navigator.clipboard?.writeText(payload)
    } catch {
      // ignore — clipboard API can be unavailable in some Electron contexts
    }
  }

  if (events.length === 0) return null

  return (
    <div style={{
      borderTop: '1px solid var(--border)',
      background: 'var(--bg-panel)',
      flexShrink: 0,
    }}>
      <button
        onClick={() => setOpen((p) => !p)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 14px', background: 'transparent',
          border: 'none', borderBottom: open ? '1px solid var(--border)' : 'none',
          color: 'var(--text-2)', fontSize: 10, fontWeight: 700,
          fontFamily: 'var(--fh)', letterSpacing: '.06em', textTransform: 'uppercase',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ width: 12, display: 'inline-block', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>▸</span>
        Event Log
        <span style={{ opacity: 0.5, fontWeight: 500, letterSpacing: 0, textTransform: 'none' }}>
          ({events.length} event{events.length !== 1 ? 's' : ''})
        </span>
        <span style={{ flex: 1 }} />
        {open && (
          <span
            onClick={(e) => { e.stopPropagation(); setFilterErrors((p) => !p) }}
            style={{
              padding: '2px 8px', borderRadius: 4,
              border: '1px solid var(--border)',
              background: filterErrors ? 'rgba(234,179,8,.18)' : 'transparent',
              color: filterErrors ? 'var(--warn)' : 'var(--text-3)',
              fontSize: 9, fontWeight: 700, letterSpacing: '.04em',
            }}
          >
            {filterErrors ? 'ONLY WARN/ERROR' : 'ALL LEVELS'}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          maxHeight: 240, overflowY: 'auto',
          fontFamily: 'monospace', fontSize: 10, lineHeight: 1.5,
          padding: '6px 14px',
        }}>
          {visible.length === 0 ? (
            <div style={{ color: 'var(--text-3)', padding: '8px 0', textAlign: 'center' }}>
              {t.rndEventNoMatch}
            </div>
          ) : (
            visible.map((ev, i) => {
              const lvl = (ev.level || 'INFO').toUpperCase()
              const color = EVENT_LEVEL_COLORS[lvl] || 'var(--text-2)'
              const t = (ev.timestamp || '').slice(11, 19)
              return (
                <div
                  key={`${ev.timestamp}-${ev.event}-${i}`}
                  onClick={() => copyEvent(ev)}
                  title="Click để copy event JSON"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '60px 60px 1fr',
                    gap: 8, padding: '3px 4px', borderRadius: 4,
                    cursor: 'pointer',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,.04)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <span style={{ color: 'var(--text-3)' }}>{t}</span>
                  <span style={{ color, fontWeight: 700 }}>{lvl}</span>
                  <span style={{ color: 'var(--text-1)' }}>
                    <span style={{ color: 'var(--text-3)' }}>{ev.event}</span>
                    {ev.message && (
                      <>
                        <span style={{ opacity: 0.5 }}> · </span>
                        {ev.message}
                      </>
                    )}
                    {ev.error_code && (
                      <span style={{ marginLeft: 6, color: 'var(--fail)', opacity: 0.8 }}>
                        [{ev.error_code}]
                      </span>
                    )}
                  </span>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
