/**
 * StoryMonitor — Story v2 phase 3 (F4b): live render progress over the cue sheet.
 *
 * Binds the shared render socket (job / parts / summary + per-cue messages) and,
 * as a reattach / polling fallback, the persisted StoryPlan v2
 * (/api/jobs/{id}/story-plan). Surfaces: a stage rail (Analyze → Visuals →
 * Narration → Render → Done) + %, a "now rendering" cue card, a per-cue strip,
 * an activity feed, and the finished video. Studio BASE tokens only.
 */
import { useEffect, useState } from 'react'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { BASE_URL } from '../../api/client'
import { fetchJobStoryPlan, type StoryPlanV2 } from '../../api/story'
import { visualColorMap } from './PlanReview/helpers'

const PHASES_VI = ['Phân tích', 'Dựng hình', 'Lời kể', 'Render', 'Xong']
const PHASES_EN = ['Analyze', 'Visuals', 'Narration', 'Render', 'Done']

function phaseIdx(stage: string | null, pct: number, terminal: boolean, ok: boolean): number {
  if (terminal) return ok ? 4 : 3
  const s = (stage || '').toLowerCase()
  if (s.includes('done')) return 4
  if (s.includes('render') || s.includes('writ') || s.includes('report') || s.includes('final') || s.includes('assembl')) return 3
  if (s.includes('segment') || s.includes('build')) return pct >= 42 ? 2 : 1
  return 0
}

function visualUrl(jobId: string, vid: string): string {
  return `${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/story-visual/${encodeURIComponent(vid)}`
}

/** A key-visual image (real thumbnail); falls back to a colour badge if the image
 * hasn't landed yet or was pruned after the render. */
function VisualThumb({ url, color, label }: { url?: string; color: string; label: string }) {
  const [failed, setFailed] = useState(false)
  if (url && !failed) return <img className="st-vt-img" src={url} alt={label} onError={() => setFailed(true)} />
  return <span className="st-vt-ph" style={{ background: color }}>{label}</span>
}

export function StoryMonitor({ vi, jobId, onDone, onNew }: {
  vi: boolean
  jobId: string | null
  onDone: () => void
  onNew: () => void
}) {
  const { stage, jobStatus, progress, liveParts, liveEvents, isTerminal } = useRenderSocket(jobId)
  const [plan, setPlan] = useState<StoryPlanV2 | null>(null)

  // Poll the persisted plan (survives reattach / WS→polling) and KEEP refreshing
  // while the render runs — the pipeline persists render.visual_assets one image at
  // a time (V2), so re-polling is how the visuals grid fills in. Stops at terminal.
  useEffect(() => {
    if (!jobId) return
    let alive = true
    const tick = () => {
      void fetchJobStoryPlan(jobId).then((r) => {
        if (alive && r.available && r.plan) setPlan(r.plan)
      }).catch(() => {})
    }
    tick()
    if (isTerminal) return () => { alive = false }
    const t = setInterval(tick, 2500)
    return () => { alive = false; clearInterval(t) }
  }, [jobId, isTerminal])

  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'
  const failed = jobStatus === 'failed'
  const partial = liveParts.some((p) => p.status === 'failed') && ok
  const phases = vi ? PHASES_VI : PHASES_EN
  const pi = phaseIdx(stage, pct, isTerminal, ok)

  const colors = plan ? visualColorMap(plan.visuals) : {}
  const cues = [...liveParts].sort((a, b) => a.part_no - b.part_no)
  const current = cues.find((p) => p.status === 'rendering') || (isTerminal ? undefined : cues.find((p) => p.status !== 'done' && p.status !== 'failed'))
  const curBeat = current && plan ? plan.timeline[current.part_no - 1] : undefined
  const curVisual = curBeat?.visual_id || current?.message || ''

  const outputPart = liveParts.find((p) => p.output_file)
  const streamUrl = outputPart ? `${BASE_URL}/api/jobs/${jobId}/parts/${outputPart.part_no}/stream` : ''

  return (
    <>
      {/* Header rail + progress */}
      <div className="st-card">
        <div className="st-mon-rail">
          {phases.map((label, i) => (
            <div key={label} className={`st-mon-ph${i === pi && !isTerminal ? ' is-active' : ''}${i < pi || (isTerminal && ok) ? ' is-done' : ''}`}>
              <span className="st-mon-ph-dot">{i < pi || (isTerminal && ok) ? '✓' : i + 1}</span>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <div className="st-mon-bar"><span className="st-mon-fill" style={{ width: `${Math.max(2, pct)}%` }} /></div>
        <div className="st-mon-meta">
          <span>{pct}%</span>
          {plan?.render?.total_sec ? <span>~{Math.round(plan.render.total_sec)}s</span> : null}
          {partial && <span className="st-badge st-badge--warn">{vi ? 'Một phần lỗi' : 'Partial'}</span>}
          {failed && <span className="st-badge st-badge--fail">{vi ? 'Thất bại' : 'Failed'}</span>}
        </div>
      </div>

      {/* Visuals grid — fills in as each key-visual renders (V2/V3) */}
      {jobId && plan && plan.visuals.length > 0 && (
        <div className="st-card">
          <div className="st-card-hd">
            <span className="st-card-title">{vi ? 'Hình' : 'Visuals'}</span>
            <span className="st-card-aside">
              {Object.keys(plan.render?.visual_assets || {}).length}/{plan.visuals.length}
            </span>
          </div>
          <div className="st-vt-grid">
            {plan.visuals.map((v) => {
              const has = !!plan.render?.visual_assets?.[v.id]
              return (
                <div key={v.id} className={`st-vt st-vt--${plan.aspect_ratio.replace(':', '-')}`}
                  style={{ borderColor: colors[v.id] }}>
                  {has
                    ? <VisualThumb url={visualUrl(jobId, v.id)} color={colors[v.id]} label={v.id} />
                    : <>
                        <span className="st-vt-ph" style={{ background: colors[v.id] }}>{v.id}</span>
                        {!isTerminal && <span className="st-visual-spin" aria-hidden />}
                      </>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Now rendering (live) */}
      {!isTerminal && (
        <div className="st-card st-mon-now">
          {curVisual && (
            <span className="st-tl-badge" style={{ background: colors[curVisual] || 'var(--border)' }}>
              {jobId && plan?.render?.visual_assets?.[curVisual]
                ? <img src={visualUrl(jobId, curVisual)} alt={curVisual} />
                : <span>{current?.part_no || ''}</span>}
            </span>
          )}
          <div className="st-mon-now-body">
            <div className="st-muted">
              {vi ? `Cue ${current?.part_no || 0}/${cues.length || plan?.timeline.length || 0}` : `Cue ${current?.part_no || 0}/${cues.length || plan?.timeline.length || 0}`}
              {pi === 1 && ` · 🖼 ${vi ? 'sinh hình' : 'visuals'}`}
              {pi === 2 && ` · 🎙 ${vi ? 'lời kể' : 'narration'}`}
              {pi === 3 && ` · 🎬 ${vi ? 'ghép cue' : 'compose'}`}
            </div>
            {curBeat && <div className="st-mon-now-narr">{curBeat.narration}</div>}
          </div>
        </div>
      )}

      {/* Cue strip */}
      {cues.length > 0 && (
        <div className="st-card">
          <div className="st-mon-strip">
            {cues.map((p) => (
              <span key={p.part_no} title={`cue ${p.part_no} · ${p.status}`}
                className={`st-mon-cue is-${p.status}`}
                style={p.status === 'done' ? { background: colors[plan?.timeline[p.part_no - 1]?.visual_id || ''] || 'var(--ok)' } : undefined} />
            ))}
          </div>
        </div>
      )}

      {/* Finished video */}
      {isTerminal && ok && streamUrl && (
        <div className="st-card">
          <video className="st-mon-video" src={streamUrl} controls />
        </div>
      )}

      {/* Activity feed */}
      {liveEvents.length > 0 && (
        <div className="st-card">
          <div className="st-card-hd"><span className="st-card-title">{vi ? 'Hoạt động' : 'Activity'}</span></div>
          <ul className="st-feed">
            {liveEvents.slice(-8).map((e, i) => (
              <li key={i} className={`st-feed-row st-feed--${(e.level || 'info').toLowerCase()}`}>
                <span className="st-feed-ev">{e.step || e.event}</span>
                <span>{e.message || ''}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="st-actions st-actions--split">
        <button type="button" className="st-btn" onClick={onNew}>{vi ? '+ Truyện mới' : '+ New story'}</button>
        <button type="button" className="st-btn st-btn--primary" onClick={onDone}>{vi ? 'Xem lịch sử ›' : 'Open History ›'}</button>
      </div>
    </>
  )
}
