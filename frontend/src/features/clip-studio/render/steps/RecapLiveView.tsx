/**
 * RecapLiveView — "Now Rendering" live-build view for render_format="recap".
 *
 * Layout (design D): two columns inside the render screen —
 *   • LEFT  "focus": the scene being rendered right now — a large preview
 *     placeholder, title, source time range, audio mode, scene progress bar and
 *     the AI narration line.
 *   • RIGHT "queue": episodes (Tập) grouped + collapsible. A finished episode
 *     collapses; the active one expands; pending ones stay folded. Episode chips
 *     at the top jump to a section. The queue scrolls; the focus stays put.
 *
 * Data (all from the WebSocket stream — no extra fetch):
 *   • recap.plan.ready  → { episodes[], scenes[{n,ep,act,start,end,dur,title,mode,climax}] }
 *   • liveParts         → per-scene status + progress (part_no === scene.n)
 *   • voice_*_completed → narration preview per scene
 *
 * Returns null until recap.plan.ready arrives, so clips mode is unaffected.
 */
import { useState } from 'react'
import type { JobPart } from '@/types/api'
import type {
  WsLogEvent,
  RecapPlanReadyContext,
  RecapSceneBlock as SceneBlock,
  RecapEpisodeInfo as EpisodeInfo,
} from '@/websocket/events'
import { StoryModelCard } from '@/features/jobs/StoryModelCard'
import type { Strings } from '../i18n'

type EpState = 'done' | 'active' | 'pending'

function _norm(status: string | undefined): string { return (status || '').toLowerCase() }
function _isActive(status: string | undefined): boolean {
  return ['rendering', 'cutting', 'transcribing'].includes(_norm(status))
}
function _isDone(status: string | undefined): boolean { return _norm(status) === 'done' }
function _isFailed(status: string | undefined): boolean { return ['failed', 'cancelled'].includes(_norm(status)) }

// Short status label + colour for a scene. P1.2 — labels come from the
// Strings table instead of hardcoded VI.
function _statusInfo(status: string | undefined, t: Strings): { color: string; label: string } {
  switch (_norm(status)) {
    case 'done':         return { color: 'var(--accent, #10b981)', label: t.rndStatusDone }
    case 'rendering':    return { color: '#f59e0b', label: t.rndStatusRendering }
    case 'cutting':      return { color: '#f59e0b', label: t.rndStatusCutting }
    case 'transcribing': return { color: '#f59e0b', label: t.rndStatusTranscribing }
    case 'failed':
    case 'cancelled':    return { color: '#ef4444', label: t.rndStatusFailed }
    default:             return { color: 'var(--text-3, #888)', label: t.rndStatusWaiting }
  }
}
// Node glyph for the queue list.
function _glyph(status: string | undefined): string {
  if (_isDone(status)) return '✓'
  if (_isActive(status)) return '◉'
  if (_isFailed(status)) return '✕'
  return '○'
}
function _fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function RecapLiveView({
  recapPlan,
  liveEvents,
  liveParts,
  t,
}: {
  recapPlan?: WsLogEvent | null
  liveEvents: WsLogEvent[]
  liveParts: JobPart[]
  t: Strings
}) {
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({})

  const planEv = recapPlan ?? [...liveEvents].reverse().find((e) => e.event === 'recap.plan.ready')
  if (!planEv) return null

  // Single typed cast at the WS boundary — WsLogEvent.context is Record<
  // string, unknown> by design; RecapPlanReadyContext pins the recap.plan.ready
  // shape (backend/tests/test_recap_plan_ready_ws_shape.py keeps it in sync).
  const ctx = (planEv.context ?? {}) as RecapPlanReadyContext
  const scenes: SceneBlock[] = (ctx.scenes ?? []).filter(Boolean)
  const episodes: EpisodeInfo[] = (ctx.episodes ?? []).filter(Boolean)
  // Story Intelligence — what the AI understood before it edited (recap pass-1).
  // Shipped in the recap.plan.ready context; rendered in the left column.
  const storyModel = ctx.story_model ?? null

  const partByNo = new Map<number, JobPart>(liveParts.map((p) => [p.part_no, p]))
  const previews = new Map<number, string>()
  for (const e of liveEvents) {
    if (e.event === 'voice_ai_rewrite_completed' || e.event === 'voice_tts_completed') {
      const pn = Number(e.context?.part_no)
      const pv = String(e.context?.first_segment_preview || '')
      if (!Number.isNaN(pn) && pv) previews.set(pn, pv)
    }
  }
  const doneCount = scenes.filter((s) => _isDone(partByNo.get(s.n)?.status)).length

  if (scenes.length === 0) {
    return (
      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text-3)' }}>
        {t.rndRecapPlanning}
      </div>
    )
  }

  // Group scenes by episode, in order.
  const epOrder: number[] = []
  const byEpisode = new Map<number, SceneBlock[]>()
  for (const sc of scenes) {
    if (!byEpisode.has(sc.ep)) { byEpisode.set(sc.ep, []); epOrder.push(sc.ep) }
    byEpisode.get(sc.ep)!.push(sc)
  }
  const epState = (ep: number): EpState => {
    const ss = byEpisode.get(ep)!
    if (ss.every((s) => _isDone(partByNo.get(s.n)?.status))) return 'done'
    if (ss.some((s) => _isActive(partByNo.get(s.n)?.status) || _isDone(partByNo.get(s.n)?.status))) return 'active'
    return 'pending'
  }

  // Focus scene: the active one nearest completion → else earliest not-done →
  // else the last scene (all done / assembling).
  const actives = scenes
    .filter((s) => _isActive(partByNo.get(s.n)?.status))
    .sort((a, b) => (partByNo.get(b.n)?.progress_percent ?? 0) - (partByNo.get(a.n)?.progress_percent ?? 0))
  const focus = actives[0]
    ?? scenes.find((s) => !_isDone(partByNo.get(s.n)?.status))
    ?? scenes[scenes.length - 1]
  const allDone = scenes.every((s) => _isDone(partByNo.get(s.n)?.status))

  const isCollapsed = (ep: number): boolean => collapsed[ep] ?? (epState(ep) !== 'active')

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', borderTop: '1px solid var(--border)' }}>
      {/* ── LEFT: focus on the scene rendering now ──────────────────────── */}
      <div style={{ width: 360, flexShrink: 0, borderRight: '1px solid var(--border)', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, color: 'var(--text-3)' }}>
          {allDone ? t.rndRecapAssembling : t.rndRecapBuildingLbl}
        </div>
        {focus && <FocusCard sc={focus} part={partByNo.get(focus.n)} preview={previews.get(focus.n)} epTitle={episodes[focus.ep]?.title || t.rndRecapEpisodeN(focus.ep + 1)} t={t} />}
        <StoryModelCard storyModel={storyModel} />
      </div>

      {/* ── RIGHT: grouped, collapsible queue ───────────────────────────── */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Episode chips */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '10px 12px 6px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-2)', marginRight: 4, alignSelf: 'center' }}>
            {t.rndRecapScenesShort(doneCount, scenes.length)}
          </span>
          {epOrder.map((ep) => {
            const st = epState(ep)
            return (
              <button
                key={ep}
                onClick={() => document.getElementById(`recap-ep-${ep}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                style={{
                  fontSize: 9, fontWeight: 700, fontFamily: 'var(--fb)', cursor: 'pointer',
                  padding: '3px 8px', borderRadius: 99, border: '1px solid var(--border)',
                  background: st === 'active' ? 'rgba(245,158,11,.15)' : 'transparent',
                  color: st === 'done' ? 'var(--accent, #10b981)' : st === 'active' ? '#f59e0b' : 'var(--text-3)',
                }}
              >
                {st === 'done' ? '✓ ' : st === 'active' ? '● ' : ''}{t.rndRecapEpisodeN(ep + 1)}
              </button>
            )
          })}
        </div>

        {/* Episode sections */}
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '4px 0 8px' }}>
          {epOrder.map((ep) => {
            const epScenes = byEpisode.get(ep)!
            const st = epState(ep)
            const epDone = epScenes.filter((s) => _isDone(partByNo.get(s.n)?.status)).length
            const epTitle = episodes[ep]?.title || t.rndRecapEpisodeN(ep + 1)
            const folded = isCollapsed(ep)
            const headColor = st === 'done' ? 'var(--accent, #10b981)' : st === 'active' ? '#f59e0b' : 'var(--text-3)'
            return (
              <div key={ep} id={`recap-ep-${ep}`}>
                {/* Episode header (toggle) */}
                <div
                  onClick={() => setCollapsed((c) => ({ ...c, [ep]: !folded }))}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
                    padding: '8px 12px', position: 'sticky', top: 0, zIndex: 1,
                    background: 'var(--bg-panel, #16161c)', borderBottom: '1px solid var(--border)',
                  }}
                >
                  <span style={{ fontSize: 10, color: 'var(--text-3)', width: 10 }}>{folded ? '▸' : '▾'}</span>
                  <span style={{ fontSize: 11, color: headColor }}>{st === 'done' ? '✅' : st === 'active' ? '◉' : '⏸'}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-1)', flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {epTitle}
                  </span>
                  <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>{epDone}/{epScenes.length}</span>
                  <span style={{ width: 46, height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                    <span style={{ display: 'block', height: '100%', width: `${epScenes.length ? (epDone / epScenes.length) * 100 : 0}%`, background: headColor }} />
                  </span>
                </div>

                {/* Scene rows */}
                {!folded && epScenes.map((sc) => {
                  const part = partByNo.get(sc.n)
                  const si = _statusInfo(part?.status, t)
                  const isOrig = sc.mode === 'original'
                  const isFocus = focus?.n === sc.n
                  return (
                    <div
                      key={sc.n}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px 5px 14px',
                        borderLeft: isFocus ? '2px solid #f59e0b' : '2px solid transparent',
                        background: isFocus ? 'rgba(245,158,11,.07)' : 'transparent',
                      }}
                    >
                      <span style={{ fontSize: 11, color: si.color, width: 12, textAlign: 'center' }}>{_glyph(part?.status)}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 11, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          <span style={{ color: 'var(--text-3)' }}>#{sc.n}</span> {sc.title || t.rndRecapSceneN(sc.n)}
                          {sc.climax && <span style={{ marginLeft: 4 }}>★</span>}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
                          {_fmt(sc.start)}–{_fmt(sc.end)} · {isOrig ? t.rndRecapOriginalAudio : t.rndRecapNarration}
                        </div>
                      </div>
                      <span style={{ fontSize: 8.5, fontWeight: 700, color: si.color, fontFamily: 'var(--fb)', flexShrink: 0 }}>
                        {_isActive(part?.status) && (part?.progress_percent ?? 0) > 0 ? `${Math.round(part!.progress_percent!)}%` : si.label}
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Left focus card ───────────────────────────────────────────────────────────
function FocusCard({ sc, part, preview, epTitle, t }: {
  sc: SceneBlock; part: JobPart | undefined; preview: string | undefined; epTitle: string; t: Strings
}) {
  const si = _statusInfo(part?.status, t)
  const isOrig = sc.mode === 'original'
  const pct = _isActive(part?.status) ? Math.max(2, Math.round(part?.progress_percent ?? 0)) : (_isDone(part?.status) ? 100 : 0)
  const line = isOrig
    ? t.rndRecapOriginalLine
    : (preview || (_isActive(part?.status) ? t.rndRecapNarrWriting : t.rndRecapNarrWaiting))
  return (
    <>
      {/* Preview placeholder (a real scene frame isn't available mid-render) */}
      <div style={{
        aspectRatio: '16 / 9', borderRadius: 10, border: '1px solid var(--border)',
        background: 'linear-gradient(135deg, rgba(245,158,11,.10), rgba(168,85,247,.10))',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
        position: 'relative', overflow: 'hidden',
      }}>
        <span style={{ fontSize: 34, fontWeight: 800, color: 'var(--text-1)', opacity: 0.9 }}>#{sc.n}</span>
        <span style={{ fontSize: 18 }}>{isOrig ? '🔊' : '🎙'}</span>
        <span style={{
          position: 'absolute', top: 8, right: 10, fontSize: 9, fontWeight: 700, color: '#fff',
          background: si.color, borderRadius: 4, padding: '2px 6px', fontFamily: 'var(--fb)',
        }}>{si.label}</span>
        {sc.climax && <span style={{ position: 'absolute', top: 8, left: 10, fontSize: 12 }} title={t.rndRecapClimax}>★</span>}
      </div>

      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.3 }}>
          {sc.title || t.rndRecapSceneN(sc.n)}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--fb)', marginTop: 3 }}>
          ⏱ {_fmt(sc.start)}–{_fmt(sc.end)}  ·  {isOrig ? t.rndRecapOriginalAudio : t.rndRecapNarration}  ·  {epTitle}
        </div>
      </div>

      {/* Scene progress */}
      <div style={{ height: 6, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: si.color, transition: 'width .3s' }} />
      </div>

      {/* Narration line */}
      <div style={{
        fontSize: 11, lineHeight: 1.5, color: isOrig ? '#c084fc' : 'var(--text-2)',
        fontFamily: 'var(--fb)', fontStyle: preview || isOrig ? 'normal' : 'italic',
        opacity: preview || isOrig ? 1 : 0.6,
        background: 'var(--bg-card, rgba(255,255,255,.03))', borderRadius: 8, padding: '8px 10px',
      }}>
        💬 {line}
      </div>
    </>
  )
}
