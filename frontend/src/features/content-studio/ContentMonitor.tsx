/**
 * ContentMonitor.tsx — Content Studio phase 3 (live render monitor) with the
 * "now rendering" scene view + terminal result + publish-metadata generation
 * (CM-9 split). Extracted verbatim from ContentStudio.tsx.
 *
 * Redesign (2026-07-07): the live monitor now surfaces the Content-Mode pipeline
 * the backend actually runs — a Content Director header (topic/tone/audience/
 * target/BGM/subtitle), a Script→Plan→Compose→Assemble→Done phase rail, a visual
 * provider-fallback banner (content.visual.fallback), and per-scene rows that
 * read the FULL plan (role, narration, emotion, reading speed, visual hint,
 * duration, transition) instead of just role+narration. Data merges the `plan`
 * prop (richest) with the latched content.plan.ready WS event (survives reattach).
 */
import { Fragment, useMemo, useState } from 'react'
import type { JobPart } from '@/types/api'
import type { WsLogEvent } from '../../websocket/events'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { Button } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { ConicRing } from '../../components/ui/ConicRing'
import { IconCheck } from '../../components/icons'
import { revealInFolder } from '../../lib/revealInFolder'
import { BASE_URL } from '../../api/client'
import { publishMeta, type ContentPlan, type ContentScene, type PublishMeta } from '../../api/content'
import { Stepper, HeroHeader, PublishField } from './shared'
import type { SceneMeta } from './types'

// ── Content phase rail ──────────────────────────────────────────────────────
// Maps the backend JobStage transitions (STARTING → ANALYZING/SEGMENT_BUILDING →
// RENDERING/RENDERING_PARALLEL → WRITING_REPORT → DONE) onto the 5 user-facing
// Content-Mode phases. Kept intentionally coarse so a stage rename degrades to a
// sensible phase rather than a blank rail.
function contentPhaseIdx(stage: string | null, isTerminal: boolean, ok: boolean): number {
  const s = (stage || '').toLowerCase()
  if (isTerminal) return ok ? 4 : 3
  if (s.includes('done')) return 4
  if (s.includes('writ') || s.includes('report') || s.includes('assembl') || s.includes('final')) return 3
  if (s.includes('render')) return 2
  if (s.includes('analyz') || s.includes('segment') || s.includes('plan') || s.includes('start')) return 1
  return 1
}

export function ContentMonitor({ jobId, onNew, vi, plan, voiceLang }: {
  jobId: string; onNew: () => void; vi: boolean; plan: ContentPlan | null; voiceLang: string
}) {
  const { stage, jobStatus, jobMessage, progress, liveParts, liveEvents, isTerminal, error } = useRenderSocket(jobId)
  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'
  // The finished video — content repoints every scene part at the assembled
  // output, so the first part with an output_file is the deliverable.
  const outputPart = liveParts.find((p) => p.output_file)
  const outputFile = outputPart?.output_file || ''
  const streamUrl = outputPart ? `${BASE_URL}/api/jobs/${jobId}/parts/${outputPart.part_no}/stream` : ''
  const [pubBusy, setPubBusy] = useState(false)
  const [pubMeta, setPubMeta] = useState<PublishMeta | null>(null)
  const [pubErr, setPubErr] = useState<string | null>(null)

  async function genPublish() {
    if (pubBusy || !plan) return
    setPubBusy(true); setPubErr(null)
    try {
      const sample = (plan.scenes || []).slice(0, 6).map((s) => s.narration).join(' ')
      const { meta } = await publishMeta({
        topic: plan.topic, tone: plan.tone, audience: plan.audience,
        voice_language: voiceLang, narration_sample: sample,
      })
      setPubMeta(meta)
    } catch (e) {
      setPubErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPubBusy(false)
    }
  }

  // Latched content.plan.ready event — survives job reattach (badge/dock) where
  // the `plan` prop is null. Header + scene rows merge both sources.
  const planEv = useMemo(
    () => [...liveEvents].reverse().find((e) => e.event === 'content.plan.ready'),
    [liveEvents],
  )
  const pctx = (planEv?.context ?? {}) as Record<string, unknown>
  const evScenes = (pctx.scenes as SceneMeta[] | undefined) ?? []
  const planReady = !!planEv || !!plan

  const info = {
    topic:    plan?.topic || (pctx.topic as string) || '',
    tone:     plan?.tone || (pctx.tone as string) || '',
    audience: plan?.audience || (pctx.audience as string) || '',
    language: plan?.language || (pctx.language as string) || voiceLang,
    bgm:      plan?.bgm_mood || (pctx.bgm_mood as string) || '',
    subStyle: plan?.subtitle_style || (pctx.subtitle_style as string) || '',
    targetSec: plan?.total_target_sec || (pctx.total_target_sec as number) || 0,
    sceneCount: plan?.scenes.length || evScenes.length || liveParts.length,
  }

  // The Content Director's plan-phase "thinking" — the newest narration/timing
  // refinement message (liveEvents is newest-first). Shown only while planning.
  const directorMsg = useMemo(() => {
    const e = liveEvents.find((ev) => ['content.narration.refined', 'content.timing.fit', 'content.narration.audit'].includes(ev.event))
    return e?.message || ''
  }, [liveEvents])

  // content.visual.fallback — a requested online visual provider (AI image/video/
  // stock) that silently fell back to the plain background on ≥1 scene. Surfaced
  // as a banner so "AI images" producing only backgrounds isn't a mystery.
  const fallbackMsg = useMemo(
    () => liveEvents.find((e) => e.event === 'content.visual.fallback')?.message || '',
    [liveEvents],
  )

  const phaseIdx = contentPhaseIdx(stage, isTerminal, ok)
  const PHASES = vi
    ? ['Kịch bản', 'Kế hoạch', 'Dựng cảnh', 'Ghép nối', 'Hoàn tất']
    : ['Script', 'Plan', 'Compose', 'Assemble', 'Done']

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={3} />
      <HeroHeader icon="🎞️" title={vi ? 'Đang render…' : 'Rendering…'}
        subtitle={jobMessage || stage || ''} />

      {/* ── Content Director header — topic + plan metadata + phase rail ──── */}
      <section className="cs-card cs-director">
        <div className="cs-director-hd">
          <span className="cs-director-topic" title={info.topic}>
            🎬 {info.topic || (vi ? 'Video nội dung' : 'Content video')}
          </span>
          <div className="cs-director-badges">
            {info.tone && <span className="cs-badge">{info.tone}</span>}
            {info.audience && <span className="cs-badge">{info.audience}</span>}
            {info.language && <span className="cs-badge cs-badge--muted">{info.language}</span>}
          </div>
        </div>

        <div className="cs-director-chips">
          {info.sceneCount > 0 && <span className="cs-chip">🎯 {info.sceneCount} {vi ? 'cảnh' : 'scenes'}</span>}
          {info.targetSec > 0 && <span className="cs-chip">⏱ ~{Math.round(info.targetSec)}s</span>}
          {info.bgm && <span className="cs-chip">🎵 {info.bgm}</span>}
          {info.subStyle && <span className="cs-chip">💬 {info.subStyle}</span>}
          <span className="cs-chip cs-chip--muted">🎙 {voiceLang}</span>
        </div>

        {/* Phase rail */}
        <div className="cs-phases">
          {PHASES.map((label, i) => {
            const state = i < phaseIdx ? 'done' : i === phaseIdx ? 'active' : 'pending'
            return (
              <span key={label} className={`cs-ph is-${state}`}>
                <span className="cs-ph-dot">{state === 'done' ? <IconCheck size={9} /> : null}</span>
                <span className="cs-ph-lbl">{label}</span>
              </span>
            )
          })}
        </div>

        <ProgressBar value={pct} variant={isTerminal ? (ok ? 'success' : 'error') : 'default'} />
        <div className="cs-hint">
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>
          {planReady && <> · {vi ? 'kế hoạch sẵn sàng' : 'plan ready'}</>}
          {!isTerminal && phaseIdx <= 1 && directorMsg && (
            <span className="cs-director-think"> · {directorMsg}</span>
          )}
        </div>

        {fallbackMsg && (
          <div className="cs-fallback">⚠ {fallbackMsg}</div>
        )}

        <DirectorFeed vi={vi} liveEvents={liveEvents} />
      </section>

      <section className="cs-card cs-card--flush cs-live-wrap">
        <ContentLiveView
          vi={vi} plan={plan} evScenes={evScenes} liveParts={liveParts}
          assembling={!isTerminal && phaseIdx === 3} assembleMsg={jobMessage || ''}
        />
      </section>
      {isTerminal && (
        <section className="cs-card" style={{ borderColor: ok ? 'var(--ok)' : 'var(--fail)' }}>
          <div className="cs-card-hd">
            <span className="cs-card-title" style={{ color: ok ? 'var(--ok)' : 'var(--fail)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p className="cs-terminal-msg">{jobMessage || error || ''}</p>

          {ok && streamUrl && (
            <video className="cs-preview" controls src={streamUrl} />
          )}

          <div className="cs-row">
            <Button variant="primary" onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</Button>
            {ok && outputFile && window.electronAPI?.openPath && (
              <>
                <Button variant="secondary" size="sm" onClick={() => window.electronAPI?.openPath?.(outputFile)}>
                  {vi ? '▶ Phát' : '▶ Play'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => revealInFolder(outputFile)}>
                  {vi ? '📁 Mở thư mục' : '📁 Open folder'}
                </Button>
              </>
            )}
            {ok && plan && (
              <Button variant="ghost" size="sm" disabled={pubBusy} onClick={genPublish}>
                {pubBusy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? '✨ Tạo tiêu đề/mô tả (AI)' : '✨ Generate title/description (AI)')}
              </Button>
            )}
          </div>
          {pubErr && <div className="cs-hint" style={{ color: 'var(--fail)' }}>{pubErr}</div>}
          {pubMeta && (
            <div className="cs-publish">
              <PublishField vi={vi} label={vi ? 'Tiêu đề' : 'Title'} value={pubMeta.title} />
              <PublishField vi={vi} label={vi ? 'Mô tả' : 'Description'} value={pubMeta.description} multiline />
              <PublishField vi={vi} label={vi ? 'Thẻ' : 'Tags'} value={(pubMeta.tags || []).join(', ')} />
              {typeof pubMeta.thumbnail_scene_index === 'number' && pubMeta.thumbnail_scene_index >= 0 && (
                <div className="cs-hint">
                  {vi ? 'Ảnh bìa gợi ý: cảnh ' : 'Suggested thumbnail: scene '}<b>{pubMeta.thumbnail_scene_index + 1}</b>
                </div>
              )}
            </div>
          )}
        </section>
      )}
      {!isTerminal && <div style={{ marginTop: 'var(--space-3)' }}><Button variant="ghost" onClick={onNew}>{vi ? 'Tạo cái khác' : 'Start another'}</Button></div>}
    </div>
  )
}

// ── Live render: Content Director scene view ────────────────────────────────

// Scene status helpers (mirror RecapLiveView semantics).
function _lvNorm(s: string | undefined): string { return (s || '').toLowerCase() }
function _lvActive(s: string | undefined): boolean { return ['rendering', 'cutting', 'transcribing'].includes(_lvNorm(s)) }
function _lvDone(s: string | undefined): boolean { return _lvNorm(s) === 'done' }
function _lvFailed(s: string | undefined): boolean { return ['failed', 'cancelled', 'skipped'].includes(_lvNorm(s)) }
function _lvGlyph(s: string | undefined): string {
  if (_lvDone(s)) return '✓'
  if (_lvActive(s)) return '◉'
  if (_lvFailed(s)) return '✕'
  return '○'
}

// Role → accent colour. Substring match so unseen role labels still theme.
function roleAccent(role: string | undefined): string {
  const r = (role || '').toLowerCase()
  if (/hook|intro|open|teaser/.test(r)) return '#f59e0b'
  if (/cta|outro|end|close|call/.test(r)) return '#a855f7'
  if (/body|point|main|detail|explain/.test(r)) return '#38bdf8'
  return 'var(--text-3)'
}

// Normalised per-scene info merged from the plan prop (richest) then the WS event.
// The event context only carries the light fields (role/narration/emotion/speed/
// visual_hint/duration); animation/camera/ken_burns/emphasis come from the plan
// prop only (absent → their chips simply don't render).
interface SceneInfo {
  role?: string; narration?: string; scene_title?: string; emotion?: string
  reading_speed?: number; visual_hint?: string; est_duration_sec?: number
  transition_hint?: string; visual_source?: string
  animation_hint?: string; camera_hint?: string; ken_burns?: boolean; emphasis?: string[]
}
function mergeSceneInfo(fromPlan?: ContentScene, fromEv?: SceneMeta): SceneInfo {
  return {
    role: fromPlan?.role ?? fromEv?.role,
    narration: fromPlan?.narration ?? fromEv?.narration,
    scene_title: fromPlan?.scene_title ?? fromEv?.scene_title,
    emotion: fromPlan?.emotion ?? fromEv?.emotion,
    reading_speed: fromPlan?.reading_speed ?? fromEv?.reading_speed,
    visual_hint: fromPlan?.visual_hint ?? fromEv?.visual_hint,
    est_duration_sec: fromPlan?.est_duration_sec ?? fromEv?.est_duration_sec,
    transition_hint: fromPlan?.transition_hint ?? fromEv?.transition_hint,
    visual_source: fromPlan?.visual_source ?? fromEv?.visual_source,
    animation_hint: fromPlan?.animation_hint,
    camera_hint: fromPlan?.camera_hint,
    ken_burns: fromPlan?.ken_burns,
    emphasis: fromPlan?.emphasis,
  }
}

function visualLabel(info: SceneInfo, vi: boolean): string {
  const src = (info.visual_source || '').toLowerCase()
  if (src === 'color') return vi ? 'Nền màu' : 'Colour'
  if (src === 'image') return vi ? 'Ảnh' : 'Image'
  if (src === 'video') return vi ? 'Video' : 'Video'
  const hint = (info.visual_hint || '').trim()
  if (hint) return hint.length > 28 ? hint.slice(0, 27) + '…' : hint
  return ''
}

// animation_hint → chip label. Only 'title' / 'lower_third' drive a real overlay
// in content_scene_render; anything else renders no chip.
function animationLabel(hint: string | undefined, vi: boolean): string {
  const h = (hint || '').trim().toLowerCase()
  if (h === 'title') return vi ? 'Thẻ tiêu đề' : 'Title card'
  if (h === 'lower_third') return 'Lower-third'
  return ''
}
// camera_hint → chip label (image backgrounds; pan alternates L/R at render time).
function cameraLabel(hint: string | undefined, vi: boolean): string {
  const h = (hint || '').trim().toLowerCase()
  if (!h) return ''
  if (h.includes('pan')) return vi ? 'Lia máy' : 'Pan'
  if (h.includes('zoom')) return 'Zoom'
  return h.charAt(0).toUpperCase() + h.slice(1)
}
// transition_hint → glyph + friendly label (mirror content_assembler._XFADE_MAP).
function transitionLabel(hint: string | undefined, vi: boolean): { glyph: string; label: string } | null {
  const h = (hint || '').trim().toLowerCase()
  if (!h) return null
  const map: Record<string, [string, string, string]> = {
    fade:  ['⤫', 'Mờ dần', 'Fade'],
    slide: ['⇥', 'Trượt', 'Slide'],
    flash: ['✦', 'Chớp trắng', 'Flash'],
    zoom:  ['⤢', 'Zoom', 'Zoom'],
    cut:   ['✂', 'Cắt thẳng', 'Cut'],
  }
  const m = map[h]
  return m ? { glyph: m[0], label: vi ? m[1] : m[2] } : { glyph: '⤫', label: h }
}

// Shared per-scene chip strip (used by both the focus card and each queue row).
// Transition is intentionally omitted here — it's shown as a connector BETWEEN
// rows instead (transition_hint describes the boundary entering the scene).
function SceneChips({ info, vi }: { info: SceneInfo; vi: boolean }) {
  const vlabel = visualLabel(info, vi)
  const anim = animationLabel(info.animation_hint, vi)
  const cam = cameraLabel(info.camera_hint, vi)
  const emph = (info.emphasis || []).filter(Boolean).length
  const hasSpeed = typeof info.reading_speed === 'number' && Math.abs(info.reading_speed - 1) > 0.02
  const hasDur = typeof info.est_duration_sec === 'number' && info.est_duration_sec > 0
  if (!info.emotion && !hasSpeed && !vlabel && !hasDur && !anim && !cam && !info.ken_burns && emph === 0) return null
  return (
    <div className="cs-live-row-chips">
      {info.emotion && <span className="cs-mini-chip">🎭 {info.emotion}</span>}
      {hasSpeed && <span className="cs-mini-chip">⏩ ×{info.reading_speed!.toFixed(2)}</span>}
      {vlabel && <span className="cs-mini-chip">🖼 {vlabel}</span>}
      {hasDur && <span className="cs-mini-chip">⏱ ~{Math.round(info.est_duration_sec!)}s</span>}
      {anim && <span className="cs-mini-chip">🔤 {anim}</span>}
      {cam && <span className="cs-mini-chip">🎥 {cam}</span>}
      {info.ken_burns && <span className="cs-mini-chip">🅺 Ken Burns</span>}
      {emph > 0 && <span className="cs-mini-chip">★ {emph} {vi ? 'nhấn' : 'emphasis'}</span>}
    </div>
  )
}

// AI Director activity feed — the plan-phase refinement events + fallback, in a
// collapsible list. Content.* events are emitted via _emit_render_event so they
// arrive in liveEvents (newest-first); older ones age out of the 50-cap buffer.
const DIRECTOR_EVENTS = [
  'content.plan.ready', 'content.narration.refined',
  'content.timing.fit', 'content.narration.audit', 'content.visual.fallback',
]
function DirectorFeed({ vi, liveEvents }: { vi: boolean; liveEvents: WsLogEvent[] }) {
  const [open, setOpen] = useState(false)
  const items = useMemo(
    () => liveEvents.filter((e) => DIRECTOR_EVENTS.includes(e.event)).slice(0, 8),
    [liveEvents],
  )
  if (items.length === 0) return null
  return (
    <div className="cs-feed">
      <button className="cs-feed-toggle" onClick={() => setOpen((o) => !o)}>
        <span className="cs-feed-caret" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>▸</span>
        {vi ? 'Nhật ký Đạo diễn AI' : 'AI Director log'}
        <span className="cs-feed-count">{items.length}</span>
      </button>
      {open && (
        <div className="cs-feed-list">
          {items.map((e, i) => (
            <div key={`${e.timestamp}-${i}`} className={`cs-feed-row lv-${(e.level || 'info').toLowerCase()}`}>
              <span className="cs-feed-time">{(e.timestamp || '').slice(11, 19)}</span>
              <span className="cs-feed-msg">{e.message || e.event}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ContentLiveView — LEFT focus column (the scene rendering now: ConicRing +
// role + narration + sub-step strip) and a RIGHT flat scene queue with rich rows.
function ContentLiveView({ vi, plan, evScenes, liveParts, assembling, assembleMsg }: {
  vi: boolean; plan: ContentPlan | null; evScenes: SceneMeta[]; liveParts: JobPart[]
  assembling: boolean; assembleMsg: string
}) {
  const parts = liveParts
  const planScenes = plan?.scenes ?? []
  const evByN = new Map<number, SceneMeta>(evScenes.filter(Boolean).map((s) => [Number(s.n), s]))
  // part_no is 1-based (content_pipeline seeds parts with enumerate(start=1));
  // plan.scenes / the event scenes align by that index.
  const infoOf = (partNo: number): SceneInfo => mergeSceneInfo(planScenes[partNo - 1], evByN.get(partNo))

  if (parts.length === 0) {
    return <div className="cs-hint" style={{ padding: '14px 16px' }}>{vi ? 'Chờ AI lập kế hoạch cảnh…' : 'Waiting for the AI scene plan…'}</div>
  }
  const actives = [...parts].filter((p) => _lvActive(p.status))
    .sort((a, b) => (b.progress_percent ?? 0) - (a.progress_percent ?? 0))
  const focus = actives[0] ?? parts.find((p) => !_lvDone(p.status)) ?? parts[parts.length - 1]
  const doneCount = parts.filter((p) => _lvDone(p.status)).length

  const titleOf = (info: SceneInfo, p: JobPart) =>
    info.role || info.scene_title || `${vi ? 'Cảnh' : 'Scene'} ${p.part_no}`
  const statusLabel = (p: JobPart) => _lvDone(p.status) ? (vi ? 'Xong' : 'Done')
    : _lvFailed(p.status) ? (vi ? 'Lỗi' : 'Failed')
    : _lvActive(p.status) ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')

  return (
    <>
      {assembling && (
        <div className="cs-assemble-banner">
          <span className="cs-assemble-spin" />
          <span>{vi ? 'Đang ghép nối các cảnh + trộn nhạc nền…' : 'Assembling scenes + mixing background music…'}</span>
          {assembleMsg && <span className="cs-assemble-sub">{assembleMsg}</span>}
        </div>
      )}
      <div className="cs-live">
        {/* LEFT — the scene being rendered now */}
        <div className="cs-live-focus">
          <div className="cs-live-label">{vi ? 'ĐANG DỰNG CẢNH' : 'BUILDING SCENE'}</div>
          {focus && (
            <ContentFocusCard
              vi={vi} part={focus} info={infoOf(focus.part_no)}
              title={titleOf(infoOf(focus.part_no), focus)}
            />
          )}
        </div>
        {/* RIGHT — rich scene queue with transition connectors between rows */}
        <div className="cs-live-queue">
          <div className="cs-live-queue-hd">{(vi ? 'Cảnh' : 'Scenes')} {doneCount}/{parts.length}</div>
          <div className="cs-live-rows">
            {parts.map((p, i) => {
              const st = _lvNorm(p.status)
              const info = infoOf(p.part_no)
              const isFocus = focus?.part_no === p.part_no
              const accent = roleAccent(info.role)
              // Connector uses the NEXT scene's transition_hint — that field
              // describes the boundary ENTERING the later scene (assembly_stage).
              const tr = i < parts.length - 1 ? transitionLabel(infoOf(parts[i + 1].part_no).transition_hint, vi) : null
              return (
                <Fragment key={p.part_no}>
                  <div className={`cs-live-row${isFocus ? ' is-focus' : ''}`} style={isFocus ? { borderLeftColor: accent } : undefined}>
                    <span className={`cs-live-glyph st-${st}`}>{_lvGlyph(p.status)}</span>
                    <div className="cs-live-row-main">
                      <div className="cs-live-row-title">
                        <span className="cs-live-row-n">#{p.part_no}</span>
                        {info.role && <span className="cs-role-badge" style={{ color: accent, borderColor: accent }}>{info.role}</span>}
                        {!info.role && <span>{titleOf(info, p)}</span>}
                      </div>
                      {info.narration && <div className="cs-live-row-narr">{info.narration}</div>}
                      <SceneChips info={info} vi={vi} />
                      {p.message && <div className="cs-live-row-sub">{p.message}</div>}
                    </div>
                    <span className={`cs-live-row-pct st-${st}`}>
                      {_lvActive(p.status) && (p.progress_percent ?? 0) > 0 ? `${Math.round(p.progress_percent ?? 0)}%` : statusLabel(p)}
                    </span>
                  </div>
                  {tr && (
                    <div className="cs-live-connector" title={vi ? 'Chuyển cảnh' : 'Transition'}>
                      <span className="cs-conn-line" />
                      <span className="cs-conn-lbl">{tr.glyph} {tr.label}</span>
                      <span className="cs-conn-line" />
                    </div>
                  )}
                </Fragment>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}

// Sub-step strip: the composition stages inside ONE scene. Derived from the
// part's progress_percent + message (content_pipeline reports 20 at
// "synthesizing narration", ~55 at the visual step, 100 on done).
const SUBSTEPS_VI = ['Lời thoại', 'Hình ảnh', 'Phụ đề', 'Ghép']
const SUBSTEPS_EN = ['Narration', 'Visual', 'Subtitle', 'Mux']
function subStepIdx(part: JobPart): number {
  if (_lvDone(part.status)) return 4
  if (!_lvActive(part.status)) return -1
  const msg = (part.message || '').toLowerCase()
  if (msg.includes('narration') || msg.includes('synth')) return 0
  if (msg.includes('visual') || msg.includes('background') || msg.includes('unavailable')) return 1
  const p = part.progress_percent ?? 0
  if (p < 25) return 0
  if (p < 60) return 1
  return 2
}

function ContentFocusCard({ vi, part, info, title }: {
  vi: boolean; part: JobPart; info: SceneInfo; title: string
}) {
  const done = _lvDone(part.status)
  const active = _lvActive(part.status)
  const pct = active ? Math.max(2, Math.round(part.progress_percent ?? 0)) : (done ? 100 : 0)
  const statusLabel = done ? (vi ? 'Xong' : 'Done') : active ? (vi ? 'Đang dựng' : 'Rendering') : (vi ? 'Chờ' : 'Waiting')
  const narr = (info.narration || '').trim()
  const accent = roleAccent(info.role)
  const cur = subStepIdx(part)
  const steps = vi ? SUBSTEPS_VI : SUBSTEPS_EN
  return (
    <>
      <div className="cs-focus-preview">
        <ConicRing progress={pct} size={76}>{done ? <IconCheck size={24} /> : undefined}</ConicRing>
        <span className="cs-focus-n">#{part.part_no}</span>
        <span className={`cs-focus-status st-${_lvNorm(part.status)}`}>{statusLabel}</span>
      </div>
      <div>
        <div className="cs-focus-title">
          {info.role && <span className="cs-role-badge" style={{ color: accent, borderColor: accent }}>{info.role}</span>}
          <span style={{ marginLeft: info.role ? 6 : 0 }}>{title}</span>
        </div>
        <SceneChips info={info} vi={vi} />
      </div>

      {/* Sub-step strip — narration → visual → subtitle → mux */}
      <div className="cs-substeps">
        {steps.map((label, i) => {
          const state = cur >= 4 ? 'done' : i < cur ? 'done' : i === cur ? 'active' : 'pending'
          return (
            <span key={label} className={`cs-substep is-${state}`}>
              <span className="cs-substep-dot" />
              <span className="cs-substep-lbl">{label}</span>
            </span>
          )
        })}
      </div>

      <div className="cs-focus-track"><div className="cs-focus-fill" style={{ width: `${pct}%`, background: accent }} /></div>
      {narr && <div className="cs-focus-narr">💬 {narr}</div>}
      {part.message && <div className="cs-focus-sub">{part.message}</div>}
    </>
  )
}
