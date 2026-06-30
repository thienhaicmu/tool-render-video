/**
 * RecapLiveView — editor-style "live build" timeline for render_format="recap".
 *
 * Recap IS a timeline (chronological scenes), so it's shown like an NLE: each
 * episode (Tập) is a sequence with a V1 (video) track + an A1 (audio) track.
 * Scene blocks are laid out left→right, width proportional to scene duration,
 * coloured by render status; the A1 lane shows narration vs original audio.
 *
 * Data (all from the WebSocket stream — no extra fetch):
 *   • recap.plan.ready  → { episodes[], scenes[{n,ep,act,start,end,dur,title,mode,climax}] }
 *   • liveParts         → per-scene render status (part_no === scene.n)
 *   • voice_*_completed → narration script preview per scene
 *   • reaction_freeze_applied → ⏸ on a scene
 *   • recap.concat.done → "ghép xong"
 *
 * Returns null until recap.plan.ready arrives, so clips mode is unaffected.
 */
import type { ReactNode } from 'react'
import type { JobPart } from '@/types/api'
import type { WsLogEvent } from '@/websocket/events'

interface EpisodeInfo { title: string; acts: number; scenes: number }
interface SceneBlock {
  n: number; ep: number; act: number
  start: number; end: number; dur: number
  title: string; mode: string; climax: boolean
}

// Video-track block colour by render status.
function _statusColor(status: string | undefined): string {
  switch ((status || '').toLowerCase()) {
    case 'done': return 'var(--accent, #10b981)'
    case 'rendering':
    case 'cutting':
    case 'transcribing': return '#f59e0b'
    case 'failed':
    case 'cancelled': return '#ef4444'
    default: return 'var(--border, #3a3a3a)'   // queued / waiting / unknown
  }
}
function _isActive(status: string | undefined): boolean {
  return ['rendering', 'cutting', 'transcribing'].includes((status || '').toLowerCase())
}
function _fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function RecapLiveView({
  liveEvents,
  liveParts,
}: {
  liveEvents: WsLogEvent[]
  liveParts: JobPart[]
}) {
  const planEv = [...liveEvents].reverse().find((e) => e.event === 'recap.plan.ready')
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

  // Still waiting on the scene list (e.g. resume of a pre-timeline job).
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
  const scriptLines: { n: number; text: string }[] = []
  for (const sc of scenes) {
    const pv = previews.get(sc.n)
    if (pv) scriptLines.push({ n: sc.n, text: pv })
  }

  const GUTTER = 30

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
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10, fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
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
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#14b8a6', display: 'inline-block' }} />A1 thuyết minh
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#a855f7', display: 'inline-block' }} />🔊 tiếng gốc
        </span>
        <span>★ cao trào</span>
      </div>

      {/* One NLE sequence per episode */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {epOrder.map((ep) => {
          const epScenes = byEpisode.get(ep)!
          const epDur = epScenes.reduce((n, s) => n + Math.max(0.1, s.dur), 0)
          const epTitle = episodes[ep]?.title || `Tập ${ep + 1}`
          return (
            <div key={ep} style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-card, rgba(255,255,255,.02))' }}>
              {/* Sequence header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 8px', background: 'rgba(255,255,255,.04)', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-1)' }}>
                  {multiEpisode ? `🎞 ${epTitle}` : `🎞 ${epTitle}`}
                </span>
                <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
                  {epScenes.length} cảnh · ~{_fmt(epDur)}
                </span>
              </div>

              {/* V1 — video track */}
              <Track label="V1" gutter={GUTTER}>
                {epScenes.map((sc) => {
                  const part = partByNo.get(sc.n)
                  const active = _isActive(part?.status)
                  const isOrig = sc.mode === 'original'
                  return (
                    <div
                      key={sc.n}
                      title={`Cảnh ${sc.n}${sc.title ? ' · ' + sc.title : ''} · ${_fmt(sc.start)}–${_fmt(sc.end)} (${Math.round(sc.dur)}s) · ${isOrig ? 'tiếng gốc' : 'thuyết minh'} · ${part?.status || 'chờ'}`}
                      style={{
                        flexGrow: Math.max(0.1, sc.dur), flexBasis: 0, minWidth: 26,
                        height: 30, borderRadius: 4,
                        background: _statusColor(part?.status),
                        border: active ? '1.5px solid #fff' : '1px solid rgba(0,0,0,.25)',
                        borderTop: isOrig ? '2px solid #a855f7' : undefined,
                        display: 'flex', flexDirection: 'column', justifyContent: 'center',
                        padding: '0 4px', overflow: 'hidden', cursor: 'default',
                      }}
                    >
                      <span style={{ fontSize: 9, fontWeight: 700, color: '#fff', whiteSpace: 'nowrap', lineHeight: 1.1 }}>
                        {sc.n}{sc.climax ? ' ★' : ''}{frozen.has(sc.n) ? ' ⏸' : ''}{isOrig ? ' 🔊' : ''}
                      </span>
                      {sc.title && (
                        <span style={{ fontSize: 8, color: 'rgba(255,255,255,.8)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'var(--fb)' }}>
                          {sc.title}
                        </span>
                      )}
                    </div>
                  )
                })}
              </Track>

              {/* A1 — audio track (narration vs original) */}
              <Track label="A1" gutter={GUTTER}>
                {epScenes.map((sc) => {
                  const isOrig = sc.mode === 'original'
                  return (
                    <div
                      key={sc.n}
                      title={isOrig ? 'Tiếng gốc (AI để khoảnh khắc tự nói)' : 'AI thuyết minh'}
                      style={{
                        flexGrow: Math.max(0.1, sc.dur), flexBasis: 0, minWidth: 26,
                        height: 16, borderRadius: 3,
                        background: isOrig ? '#a855f7' : '#14b8a6',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '0 4px', overflow: 'hidden',
                      }}
                    >
                      <span style={{ fontSize: 8, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'var(--fb)' }}>
                        {isOrig ? '🔊 gốc' : 'thuyết minh'}
                      </span>
                    </div>
                  )
                })}
              </Track>
            </div>
          )
        })}
      </div>

      {/* Narration script — streams in as scenes get narrated */}
      {scriptLines.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4 }}>KỊCH BẢN THUYẾT MINH</div>
          <div style={{ maxHeight: 120, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, background: 'var(--bg-card)', borderRadius: 6, padding: '6px 8px' }}>
            {scriptLines.map((l) => (
              <div key={l.n} style={{ fontSize: 10, color: 'var(--text-2)', lineHeight: 1.4, fontFamily: 'var(--fb)' }}>
                <span style={{ color: 'var(--text-3)' }}>#{l.n}</span> {l.text}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** One NLE track lane: a fixed left gutter label + a proportional block row. */
function Track({ label, gutter, children }: { label: string; gutter: number; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', gap: 4, padding: '4px 6px' }}>
      <div style={{ width: gutter, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700, color: 'var(--text-3)', fontFamily: 'var(--fb)', background: 'rgba(255,255,255,.03)', borderRadius: 3 }}>
        {label}
      </div>
      <div style={{ display: 'flex', gap: 3, flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  )
}
