import React, { useState, useRef, useEffect, useMemo } from 'react'
import type { JobPart, WsProgressSummary } from '@/types/api'
import type { ClipSlot } from '../types'
import type { Strings } from '../i18n'
import type { WsLogEvent } from '@/websocket/events'
import { estimateRenderEtaSec } from '../eta'
import { stageBlendedPercent } from '../progress'
import { RecapLiveView } from './RecapLiveView'
import { RenderStage } from './RenderStage'
import { IconCheck } from '@/components/icons'
import { extendJob } from '@/api/jobs'

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
  if (s.includes('scene') || s.includes('segment') || s.includes('analyz')) return 1
  if (s.includes('download')) return 0
  return -1
}

// clipStateKey/activity/pipeline moved into RenderStage with the ClipRow
// redesign (owner-approved focus-stage layout, 2026-07-02).

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

        {/* WP1 — phase rail replaces the redundant per-clip segmented bar
            (per-clip status now lives in the ClipTile grid below). */}
        <div className="rd-phases">
          {phases.map((ph, i) => {
            if (ph.key === 'download') return null
            const state = i < activePhaseIdx ? 'done' : i === activePhaseIdx ? 'active' : 'pending'
            return (
              <span key={ph.key} className={`rd-ph rd-ph-${state}`}>
                <span className="rd-ph-dot">{state === 'done' && <IconCheck size={10} />}</span>
                <span className="rd-ph-lbl">{ph.label}</span>
              </span>
            )
          })}
        </div>

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
                  ? t.rndRecapProgress(doneCount, effTotal, recapEpisodes)
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
              ? <><span className="rd-ai-pulse" /> {t.rndAiAnalyzing}</>
              : stage === 'transcribe' && !isTerminal
              ? t.rndAiTranscribing
              : stage === 'render' && !isTerminal && isRecap && effTotal > 0
              ? t.rndRecapBuilding(effTotal, recapEpisodes || 1)
              : stage === 'render' && !isTerminal && totalCount > 0
              ? t.rndAiRendering(totalCount)
              : isTerminal && !isFailed && isRecap
              ? t.rndRecapDone(recapEpisodes || 1)
              : isTerminal && !isFailed
              ? t.rndAiDone(doneCount)
              : displayMsg || t.rndProcessing
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
                <span style={{ opacity: 0.6, fontSize: 11 }}>{t.rndStuckHint}</span>
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
                    fontSize: 11, fontWeight: 700, letterSpacing: '.04em',
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
                    fontSize: 11, fontWeight: 600,
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
            {jobMessage && <span style={{ display: 'block', fontSize: '11px', opacity: .55, marginTop: 2 }}>{jobMessage}</span>}
          </span>
        </div>
      ) : isRecap ? null : (
        <div className="rd-queue-scroll">
          <RenderStage
            slots={clipSlots}
            jobId={jobId}
            thumbRatio={thumbRatio}
            t={t}
            getStatusLabel={getStatusLabel}
          />
        </div>
      )}

      {/* R5 — recap live-build view (renders only when a recap.plan.ready event
          has arrived; null otherwise so clips mode is unaffected). */}
      <RecapLiveView recapPlan={recapPlan ?? null} liveEvents={liveEvents || []} liveParts={liveParts} t={t} />

      {/* S4.5 — event log tail panel */}
      <EventLogPanel events={liveEvents || []} t={t} />

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
          color: 'var(--text-2)', fontSize: 11, fontWeight: 700,
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
              fontSize: 10, fontWeight: 700, letterSpacing: '.04em',
            }}
          >
            {filterErrors ? 'ONLY WARN/ERROR' : 'ALL LEVELS'}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          maxHeight: 240, overflowY: 'auto',
          fontFamily: 'monospace', fontSize: 11, lineHeight: 1.5,
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
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--text-rgb),.04)' }}
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
