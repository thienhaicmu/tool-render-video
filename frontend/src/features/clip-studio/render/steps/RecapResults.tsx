/**
 * RecapResults — episode-grouped results view for render_format="recap".
 *
 * A recap job's deliverables are the assembled EPISODE videos, not the many
 * short scene-parts. The backend records job_parts as scenes but repoints each
 * scene-part's output_file to the episode file that contains it. So we group
 * the scene-parts by episode (via the recap plan scene→ep mapping) and show
 * ONE card per episode — with the story summary + act/scene structure — instead
 * of the clips-mode grid, which showed a pile of cards all playing the same
 * episode file.
 *
 * Data is 100% existing: getJobParts (parts, output_file repointed) +
 * getRecapPlan (episodes[] + scenes[{n,ep,act,dur,title,climax}] + summary).
 */
import { useMemo, useState } from 'react'
import type { JobPart } from '@/types/api'
import type { RecapPlanResponse } from '@/api/jobs'
import type { RecapSceneBlock } from '@/websocket/events'
import type { Strings } from '../i18n'
import { getPartThumbnailUrl, getPartMediaUrl } from '../utils'
import { IconFilm, IconPlay, IconCheck } from '@/components/icons'

function fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

interface EpisodeGroup {
  ep: number
  title: string
  scenes: RecapSceneBlock[]
  repPart: JobPart | null   // a done part whose output_file is the episode video
  durationSec: number
  acts: number
  hasClimax: boolean
  allDone: boolean
}

function buildEpisodes(scenes: RecapSceneBlock[], parts: JobPart[], epTitles: string[]): EpisodeGroup[] {
  const partByNo = new Map<number, JobPart>(parts.map((p) => [p.part_no, p]))
  const order: number[] = []
  const byEp = new Map<number, RecapSceneBlock[]>()
  for (const sc of scenes) {
    if (!byEp.has(sc.ep)) { byEp.set(sc.ep, []); order.push(sc.ep) }
    byEp.get(sc.ep)!.push(sc)
  }
  return order.map((ep) => {
    const epScenes = byEp.get(ep)!.slice().sort((a, b) => a.n - b.n)
    const doneParts = epScenes.map((s) => partByNo.get(s.n)).filter((p): p is JobPart => !!p && p.status === 'done')
    return {
      ep,
      title: epTitles[ep] || `Episode ${ep + 1}`,
      scenes: epScenes,
      repPart: doneParts[0] ?? null,
      durationSec: epScenes.reduce((sum, s) => sum + (s.dur || 0), 0),
      acts: new Set(epScenes.map((s) => s.act)).size,
      hasClimax: epScenes.some((s) => s.climax),
      allDone: epScenes.length > 0 && doneParts.length === epScenes.length,
    }
  })
}

export function RecapResults({ jobId, parts, recapPlan, jobStatus, aspectRatio, t, onRetry, isRetrying }: {
  jobId: string
  parts: JobPart[]
  recapPlan: RecapPlanResponse
  jobStatus: string
  aspectRatio: string
  t: Strings
  onRetry: () => void
  isRetrying: boolean
}) {
  const [openScenes, setOpenScenes] = useState<Record<number, boolean>>({})
  const [playing, setPlaying] = useState<number | null>(null)

  const scenes = (recapPlan.scenes ?? []).filter(Boolean)
  const epTitles = (recapPlan.episodes ?? []).map((e) => e?.title || '')
  const episodes = useMemo(() => buildEpisodes(scenes, parts, epTitles), [scenes, parts, epTitles])
  const doneEpisodes = episodes.filter((e) => e.repPart)
  const totalDur = doneEpisodes.reduce((s, e) => s + e.durationSec, 0)
  const thumbRatio = aspectRatio.replace(':', '/')

  const openFolder = () => {
    const f = doneEpisodes[0]?.repPart?.output_file
    if (!f) return
    const sep = f.includes('\\') ? '\\' : '/'
    const dir = f.substring(0, f.lastIndexOf(sep))
    if (dir) window.electronAPI?.openPath?.(dir)
  }

  const failed = jobStatus === 'failed'

  return (
    <div className="res-screen">
      <div className="res-left">
        {/* Hero */}
        {failed ? (
          <div className="res-hero res-hero-failed">
            <div className="res-hero-bg" />
            <div className="res-hero-content">
              <div className="res-hero-left">
                <div className="res-complete-row">
                  <div className="res-complete-icon res-failed-icon">✕</div>
                  <div>
                    <div className="res-kicker res-kicker-failed">{t.resFailedTitle}</div>
                    <div className="res-hero-title">{t.rndRecapAssembling}</div>
                  </div>
                </div>
              </div>
              <div className="res-hero-right">
                <button className="res-export-btn" onClick={onRetry} disabled={isRetrying}>
                  {isRetrying ? '…' : t.btnRetry}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="res-hero">
            <div className="res-hero-bg" />
            <div className="res-hero-content">
              <div className="res-hero-left">
                <div className="res-complete-row">
                  <div className="res-complete-icon">✓</div>
                  <div>
                    <div className="res-kicker">{t.resComplete}</div>
                    <div className="res-hero-title">
                      {t.rndRecapProgress(doneEpisodes.length, scenes.length, doneEpisodes.length)}
                    </div>
                  </div>
                </div>
              </div>
              <div className="res-hero-right">
                <div className="res-kpi-row">
                  <div className="res-kpi blue"><strong>{doneEpisodes.length}</strong><span>episode{doneEpisodes.length !== 1 ? 's' : ''}</span></div>
                  <div className="res-kpi"><strong>{scenes.length}</strong><span>scenes</span></div>
                  <div className="res-kpi"><strong>{fmt(totalDur)}</strong><span>{t.resKpiTotal}</span></div>
                </div>
                {doneEpisodes[0]?.repPart?.output_file && (
                  <button className="res-export-btn" onClick={openFolder}>{t.resOpenFolder}</button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Story summary from the recap plan */}
        {recapPlan.story_summary && (
          <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-2)', lineHeight: 1.55, display: 'flex', gap: 8 }}>
            <span style={{ color: 'var(--accent)', flexShrink: 0 }}><IconFilm size={15} /></span>
            <span>{recapPlan.story_summary}</span>
          </div>
        )}

        {/* Episode cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: 16, overflowY: 'auto' }}>
          {episodes.map((ep) => {
            const isPlaying = playing === ep.ep
            const scenesOpen = openScenes[ep.ep] ?? false
            const rp = ep.repPart
            return (
              <div key={ep.ep} style={{
                border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden',
                background: 'var(--bg-card)', display: 'flex', flexDirection: 'column',
              }}>
                <div style={{ display: 'flex', gap: 14, padding: 14 }}>
                  {/* Preview */}
                  <div style={{ width: 220, flexShrink: 0, borderRadius: 10, overflow: 'hidden', background: 'rgba(var(--text-rgb),.05)', position: 'relative', aspectRatio: thumbRatio, maxHeight: 260 }}>
                    {rp && isPlaying ? (
                      <video key={rp.part_no} src={getPartMediaUrl(jobId, rp.part_no)} controls autoPlay style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }} />
                    ) : rp ? (
                      <>
                        <img src={getPartThumbnailUrl(jobId, rp.part_no)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
                        <button onClick={() => setPlaying(ep.ep)} aria-label="Play episode" style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', background: 'rgba(0,0,0,.28)', border: 'none', cursor: 'pointer' }}>
                          <IconPlay size={28} />
                        </button>
                      </>
                    ) : (
                      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)' }}><IconFilm size={30} /></div>
                    )}
                  </div>

                  {/* Detail */}
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {ep.allDone && <span style={{ color: 'var(--status-success)', display: 'inline-flex' }}><IconCheck size={15} /></span>}
                      <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>
                        Ep {ep.ep + 1} · {ep.title}
                      </span>
                      {ep.hasClimax && <span title="Climax" style={{ color: 'var(--accent)' }}>★</span>}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      <span>{fmt(ep.durationSec)}</span>
                      <span>· {ep.scenes.length} scenes</span>
                      <span>· {ep.acts} act{ep.acts !== 1 ? 's' : ''}</span>
                    </div>

                    <div style={{ display: 'flex', gap: 8, marginTop: 'auto', flexWrap: 'wrap' }}>
                      {rp && (
                        <a className="clip-save-btn" href={getPartMediaUrl(jobId, rp.part_no)} download={rp.clip_name || `episode_${ep.ep + 1}.mp4`}>
                          Save episode
                        </a>
                      )}
                      <button className="btn-xs" onClick={() => setOpenScenes((o) => ({ ...o, [ep.ep]: !scenesOpen }))}>
                        {scenesOpen ? 'Hide scenes' : `Scenes (${ep.scenes.length})`}
                      </button>
                    </div>

                    {scenesOpen && (
                      <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 180, overflowY: 'auto' }}>
                        {ep.scenes.map((sc) => (
                          <div key={sc.n} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, padding: '2px 0', color: 'var(--text-2)' }}>
                            <span style={{ color: 'var(--text-3)', width: 28 }}>#{sc.n}</span>
                            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {sc.title || `Scene ${sc.n}`}{sc.climax ? ' ★' : ''}
                            </span>
                            <span style={{ color: 'var(--text-3)', fontFamily: 'monospace', fontSize: 10 }}>{fmt(sc.start)}–{fmt(sc.end)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
