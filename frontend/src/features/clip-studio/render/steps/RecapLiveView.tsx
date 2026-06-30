/**
 * RecapLiveView (Phase R5) — "live build" view for render_format="recap".
 *
 * Visualises the recap being assembled in real time from the WebSocket event
 * stream (no new backend data needed — all of this already flows):
 *   • recap.plan.ready  → act/scene timeline scaffold (acts + scene counts)
 *   • liveParts         → each scene lights up as it renders (scene = part)
 *   • voice_*_completed → narration script streams in (first_segment_preview)
 *   • reaction_freeze_applied → ⏸ freeze marker on a scene
 *   • recap.concat.done → "assembled" status
 *
 * Renders nothing (returns null) until a recap.plan.ready event arrives, so it
 * is safe to mount unconditionally in the rendering screen.
 */
import type { JobPart } from '@/types/api'
import type { WsLogEvent } from '@/websocket/events'

interface ActInfo { title: string; beat: string; scenes: number }
interface EpisodeInfo { title: string; acts: number; scenes: number }

const _BEAT_COLOR: Record<string, string> = {
  setup: '#3b82f6',
  rising: '#f59e0b',
  climax: '#ef4444',
  resolution: '#10b981',
}

function _sceneColor(status: string | undefined): string {
  switch (status) {
    case 'done': return 'var(--accent, #10b981)'
    case 'rendering':
    case 'cutting':
    case 'transcribing': return '#f59e0b'
    case 'failed': return '#ef4444'
    case 'skipped': return 'var(--text-3, #888)'
    default: return 'var(--border, #444)'   // queued / waiting / unknown
  }
}

export function RecapLiveView({
  liveEvents,
  liveParts,
}: {
  liveEvents: WsLogEvent[]
  liveParts: JobPart[]
}) {
  // Latest plan wins (resume/retry can re-emit).
  const planEv = [...liveEvents].reverse().find((e) => e.event === 'recap.plan.ready')
  if (!planEv) return null

  const acts = ((planEv.context?.acts as ActInfo[]) || []).filter(Boolean)
  const totalTarget = Number(planEv.context?.total_target_sec || 0)
  if (acts.length === 0) return null

  // R6: episode grouping + per-scene audio mode. Back-compat — a pre-R6 event
  // has no `episodes`; treat all acts as a single (untitled) episode.
  const episodes = ((planEv.context?.episodes as EpisodeInfo[]) || []).filter(Boolean)
  const sceneModes = (planEv.context?.scene_modes as string[]) || []
  const multiEpisode = episodes.length > 1
  // Build [start, count] act-slices per episode from the episode act-counts.
  const epSlices: { ep: EpisodeInfo; actStart: number; actCount: number }[] = []
  if (episodes.length > 0) {
    let cursor = 0
    for (const ep of episodes) {
      const n = Math.max(0, ep.acts | 0)
      epSlices.push({ ep, actStart: cursor, actCount: n })
      cursor += n
    }
  } else {
    epSlices.push({ ep: { title: '', acts: acts.length, scenes: 0 }, actStart: 0, actCount: acts.length })
  }

  const partByNo = new Map<number, JobPart>(liveParts.map((p) => [p.part_no, p]))
  const frozen = new Set<number>(
    liveEvents
      .filter((e) => e.event === 'reaction_freeze_applied')
      .map((e) => Number(e.context?.part_no))
      .filter((n) => !Number.isNaN(n)),
  )
  // Narration previews, keyed by part_no (last preview wins).
  const previews = new Map<number, string>()
  for (const e of liveEvents) {
    if (e.event === 'voice_ai_rewrite_completed' || e.event === 'voice_tts_completed') {
      const pn = Number(e.context?.part_no)
      const pv = String(e.context?.first_segment_preview || '')
      if (!Number.isNaN(pn) && pv) previews.set(pn, pv)
    }
  }
  const concatDone = liveEvents.some((e) => e.event === 'recap.concat.done')
  const concatMethod = String(
    [...liveEvents].reverse().find((e) => e.event === 'recap.concat.done')?.context?.method || '',
  )

  // Flatten scenes → global part_no (1-based, in act order).
  let partNo = 0
  const scriptLines: { pn: number; act: string; text: string }[] = []

  return (
    <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, color: 'var(--text-1)' }}>
          🎬 RECAP — LIVE BUILD
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>
          {multiEpisode ? `${episodes.length} tập · ` : ''}{acts.length} acts
          {totalTarget > 0 ? ` · ~${Math.round(totalTarget)}s` : ''}
          {concatDone ? ` · assembled (${concatMethod})` : ''}
        </span>
      </div>

      {/* Episode → act → scene timeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {epSlices.map(({ ep, actStart, actCount }, ei) => (
          <div key={ei}>
            {multiEpisode && (
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
                🎞 {ep.title || `Tập ${ei + 1}`}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: multiEpisode ? 6 : 0 }}>
              {acts.slice(actStart, actStart + actCount).map((act, ai) => {
                const beat = (act.beat || '').toLowerCase()
                const beatColor = _BEAT_COLOR[beat] || 'var(--text-3)'
                return (
                  <div key={ai}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: beatColor, display: 'inline-block' }} />
                      <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-2)' }}>
                        {act.title || `Act ${actStart + ai + 1}`}
                      </span>
                      {beat && <span style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)' }}>· {beat}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', paddingLeft: 14 }}>
                      {Array.from({ length: Math.max(0, act.scenes | 0) }).map((_, si) => {
                        partNo += 1
                        const pn = partNo
                        const part = partByNo.get(pn)
                        const preview = previews.get(pn)
                        const isOriginal = sceneModes[pn - 1] === 'original'
                        if (preview) scriptLines.push({ pn, act: act.title || `Act ${actStart + ai + 1}`, text: preview })
                        return (
                          <div
                            key={si}
                            title={`Scene ${pn}${isOriginal ? ' · original audio' : ' · narrated'}${part ? ' · ' + part.status : ''}`}
                            style={{
                              position: 'relative',
                              width: 22, height: 14, borderRadius: 3,
                              background: _sceneColor(part?.status),
                              border: isOriginal ? '1.5px solid #a855f7' : 'none',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 8, color: '#fff', fontFamily: 'var(--fb)',
                            }}
                          >
                            {frozen.has(pn) ? '⏸' : isOriginal ? '🔊' : ''}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {sceneModes.includes('original') && (
        <div style={{ marginTop: 8, fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--fb)', display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 12, height: 9, borderRadius: 2, border: '1.5px solid #a855f7', display: 'inline-block' }} />
          🔊 = giữ tiếng gốc (AI để khoảnh khắc tự nói) · còn lại = AI thuyết minh
        </div>
      )}

      {/* Narration script — streams in as scenes get narrated */}
      {scriptLines.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4 }}>
            NARRATION SCRIPT
          </div>
          <div
            style={{
              maxHeight: 120, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4,
              background: 'var(--bg-card)', borderRadius: 6, padding: '6px 8px',
            }}
          >
            {scriptLines.map((l) => (
              <div key={l.pn} style={{ fontSize: 10, color: 'var(--text-2)', lineHeight: 1.4, fontFamily: 'var(--fb)' }}>
                <span style={{ color: 'var(--text-3)' }}>#{l.pn}</span> {l.text}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
