/**
 * RecapLiveView — "live build" view for render_format="recap".
 *
 * Recap is a chronological montage, so each episode (Tập) shows:
 *   • a thin proportional progress strip (the at-a-glance shape), and
 *   • a readable SCENE LIST — one row per scene with its title, source time
 *     range, audio mode (narration vs original), live render status, and the
 *     AI narration line as it streams in — so you can tell what every scene is
 *     actually doing.
 *
 * Data (all from the WebSocket stream — no extra fetch):
 *   • recap.plan.ready  → { episodes[], scenes[{n,ep,act,start,end,dur,title,mode,climax}] }
 *   • liveParts         → per-scene render status (part_no === scene.n)
 *   • voice_*_completed → narration preview per scene
 *   • reaction_freeze_applied → ⏸ on a scene
 *   • recap.concat.done → "ghép xong"
 *
 * Returns null until recap.plan.ready arrives, so clips mode is unaffected.
 */
import type { JobPart } from '@/types/api'
import type { WsLogEvent } from '@/websocket/events'

interface EpisodeInfo { title: string; acts: number; scenes: number }
interface SceneBlock {
  n: number; ep: number; act: number
  start: number; end: number; dur: number
  title: string; mode: string; climax: boolean
}

// Per-scene render status → colour + a short Vietnamese label.
function _statusInfo(status: string | undefined): { color: string; label: string; active: boolean } {
  switch ((status || '').toLowerCase()) {
    case 'done':         return { color: 'var(--accent, #10b981)', label: 'xong',   active: false }
    case 'rendering':    return { color: '#f59e0b',                label: 'render', active: true }
    case 'cutting':      return { color: '#f59e0b',                label: 'cắt',    active: true }
    case 'transcribing': return { color: '#f59e0b',                label: 'phụ đề', active: true }
    case 'failed':
    case 'cancelled':    return { color: '#ef4444',                label: 'lỗi',    active: false }
    default:             return { color: 'var(--border, #3a3a3a)', label: 'chờ',    active: false }
  }
}
function _fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function RecapLiveView({
  recapPlan,
  liveEvents,
  liveParts,
}: {
  recapPlan?: WsLogEvent | null
  liveEvents: WsLogEvent[]
  liveParts: JobPart[]
}) {
  const planEv = recapPlan ?? [...liveEvents].reverse().find((e) => e.event === 'recap.plan.ready')
  if (!planEv) return null

  const scenes = ((planEv.context?.scenes as SceneBlock[]) || []).filter(Boolean)
  const episodes = ((planEv.context?.episodes as EpisodeInfo[]) || []).filter(Boolean)
  const totalTarget = Number(planEv.context?.total_target_sec || 0)

  const partByNo = new Map<number, JobPart>(liveParts.map((p) => [p.part_no, p]))
  const frozen = new Set<number>(
    liveEvents
      .filter((e) => e.event === 'reaction_freeze_applied')
      .map((e) => Number(e.context?.part_no))
      .filter((n) => !Number.isNaN(n)),
  )
  const previews = new Map<number, string>()
  for (const e of liveEvents) {
    if (e.event === 'voice_ai_rewrite_completed' || e.event === 'voice_tts_completed') {
      const pn = Number(e.context?.part_no)
      const pv = String(e.context?.first_segment_preview || '')
      if (!Number.isNaN(pn) && pv) previews.set(pn, pv)
    }
  }
  const concatDone = liveEvents.some((e) => e.event === 'recap.concat.done')
  const doneScenes = liveParts.filter((p) => (p.status || '').toLowerCase() === 'done').length

  if (scenes.length === 0) {
    return (
      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text-3)' }}>
        🎬 RECAP — đang dựng kế hoạch cảnh…
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
  const multiEpisode = epOrder.length > 1

  return (
    <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-1)' }}>
          🎬 RECAP — LIVE BUILD
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
          {doneScenes}/{scenes.length} cảnh
          {multiEpisode ? ` · ${epOrder.length} tập` : ''}
          {totalTarget > 0 ? ` · ~${_fmt(totalTarget)}` : ''}
          {concatDone ? ' · ✓ ghép xong' : ''}
        </span>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12, fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
        {([
          ['var(--border, #3a3a3a)', 'chờ'],
          ['#f59e0b', 'đang dựng'],
          ['var(--accent, #10b981)', 'xong'],
          ['#ef4444', 'lỗi'],
        ] as const).map(([c, lbl]) => (
          <span key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: c, display: 'inline-block' }} />{lbl}
          </span>
        ))}
        <span>🎙 thuyết minh</span>
        <span>🔊 tiếng gốc</span>
        <span>★ cao trào</span>
      </div>

      {/* Per-episode: progress strip + readable scene list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {epOrder.map((ep) => {
          const epScenes = byEpisode.get(ep)!
          const epDur = epScenes.reduce((n, s) => n + Math.max(0.1, s.dur), 0)
          const epTitle = episodes[ep]?.title || `Tập ${ep + 1}`
          const epDone = epScenes.filter((s) => (partByNo.get(s.n)?.status || '').toLowerCase() === 'done').length
          return (
            <div key={ep} style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-card, rgba(255,255,255,.02))' }}>
              {/* Episode header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 9px', background: 'rgba(255,255,255,.04)', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-1)' }}>🎞 {epTitle}</span>
                <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
                  {epDone}/{epScenes.length} cảnh · ~{_fmt(epDur)}
                </span>
              </div>

              {/* Thin proportional progress strip (the at-a-glance shape) */}
              <div style={{ display: 'flex', gap: 2, padding: '6px 9px 4px' }}>
                {epScenes.map((sc) => {
                  const st = _statusInfo(partByNo.get(sc.n)?.status)
                  return (
                    <div
                      key={sc.n}
                      title={`Cảnh ${sc.n} · ${st.label}`}
                      style={{
                        flexGrow: Math.max(0.1, sc.dur), flexBasis: 0, minWidth: 4,
                        height: 6, borderRadius: 2, background: st.color,
                        border: sc.mode === 'original' ? '1px solid #a855f7' : 'none',
                      }}
                    />
                  )
                })}
              </div>

              {/* Scene list — one readable row per scene */}
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {epScenes.map((sc, i) => {
                  const st = _statusInfo(partByNo.get(sc.n)?.status)
                  const isOrig = sc.mode === 'original'
                  const preview = previews.get(sc.n)
                  const line = isOrig
                    ? '🔊 Để tiếng gốc của phim'
                    : (preview || (st.active ? 'đang dựng lời…' : (st.label === 'xong' ? '' : 'chờ thuyết minh')))
                  return (
                    <div
                      key={sc.n}
                      style={{
                        display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 9px',
                        borderTop: i === 0 ? 'none' : '1px solid var(--border)',
                        background: st.active ? 'rgba(245,158,11,.06)' : 'transparent',
                      }}
                    >
                      {/* Status pill */}
                      <span style={{
                        flexShrink: 0, marginTop: 1, minWidth: 46, textAlign: 'center',
                        fontSize: 9, fontWeight: 700, color: '#fff', fontFamily: 'var(--fb)',
                        background: st.color, borderRadius: 4, padding: '2px 4px',
                      }}>
                        {st.label}
                      </span>
                      {/* Scene content */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-1)' }}>
                            #{sc.n} {sc.title || `Cảnh ${sc.n}`}
                          </span>
                          <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
                            {_fmt(sc.start)}–{_fmt(sc.end)}
                          </span>
                          <span style={{ fontSize: 10 }}>{isOrig ? '🔊' : '🎙'}</span>
                          {sc.climax && <span style={{ fontSize: 10 }} title="cao trào">★</span>}
                          {frozen.has(sc.n) && <span style={{ fontSize: 10 }} title="freeze">⏸</span>}
                        </div>
                        {line && (
                          <div style={{
                            fontSize: 10, color: isOrig ? '#c084fc' : 'var(--text-2)',
                            lineHeight: 1.4, fontFamily: 'var(--fb)', marginTop: 2,
                            fontStyle: (preview || isOrig) ? 'normal' : 'italic',
                            opacity: (preview || isOrig) ? 1 : 0.6,
                          }}>
                            {line}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
