/**
 * PlanReview — Story v2 phase 2 (F3): review + EDIT the StoryPlan before render.
 *
 * Three panels over the same immutable plan (edits flow up via setPlan):
 *   CharactersPanel — name · canonical_desc · voice · optional reference sheet
 *   VisualsPanel    — per key-visual prompt/negative/characters/tier + preview
 *   TimelineEditor  — the beat list (narration · visual · focus/motion/transition
 *                     · hook) with reorder / add / delete + live duration
 *
 * A locally-held ``previews`` map (visual_id → preview image url) is shared so the
 * TimelineEditor can show a thumbnail once a visual has been previewed. Uses the
 * Studio BASE (F0) only — no content-studio.
 */
import { useState } from 'react'
import type { StoryPlanV2, Beat, Visual, CharacterDef } from '../../../api/story'
import type { Aspect, StoryLang } from '../types'
import { beatEstSec, visualColorMap } from './helpers'
import { CharactersPanel } from './CharactersPanel'
import { VisualsPanel } from './VisualsPanel'
import { TimelineEditor } from './TimelineEditor'

function newBeatId(existing: Beat[]): string {
  let i = existing.length + 1
  const ids = new Set(existing.map((b) => b.id))
  while (ids.has(`b${i}`)) i++
  return `b${i}`
}

export function PlanReview({ vi, plan, setPlan, busy, artStyle, aspect, language, onRender, onBack }: {
  vi: boolean
  plan: StoryPlanV2
  setPlan: (p: StoryPlanV2) => void
  estTotal: number
  busy: boolean
  artStyle: string
  aspect: Aspect
  language: StoryLang
  onRender: () => void
  onBack: () => void
}) {
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const colors = visualColorMap(plan.visuals)
  const liveTotal = plan.timeline.reduce(
    (s, b) => s + beatEstSec(b, language) + Math.max(0, b.pause_after || 0), 0)
  const mm = Math.floor(liveTotal / 60)
  const ss = Math.round(liveTotal % 60)

  const patch = (p: Partial<StoryPlanV2>) => setPlan({ ...plan, ...p })
  const updateCharacter = (id: string, up: Partial<CharacterDef>) =>
    patch({ characters: plan.characters.map((c) => (c.id === id ? { ...c, ...up } : c)) })
  const updateVisual = (id: string, up: Partial<Visual>) =>
    patch({ visuals: plan.visuals.map((v) => (v.id === id ? { ...v, ...up } : v)) })
  const updateBeat = (id: string, up: Partial<Beat>) =>
    patch({ timeline: plan.timeline.map((b) => (b.id === id ? { ...b, ...up } : b)) })

  function moveBeat(id: string, dir: -1 | 1) {
    const t = [...plan.timeline]
    const i = t.findIndex((b) => b.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= t.length) return
    ;[t[i], t[j]] = [t[j], t[i]]
    patch({ timeline: t })
  }
  function deleteBeat(id: string) {
    if (plan.timeline.length <= 1) return
    patch({ timeline: plan.timeline.filter((b) => b.id !== id) })
  }
  function addBeatAfter(id: string) {
    const t = [...plan.timeline]
    const i = t.findIndex((b) => b.id === id)
    const ref = t[i]
    const fresh: Beat = {
      id: newBeatId(t), narration: '', speaker_id: ref?.speaker_id || '',
      visual_id: ref?.visual_id || plan.visuals[0]?.id || '',
      focus: 'center', motion: 'zoom_in', emotion: 'normal',
      reading_speed: 1, pause_after: 0, hold_sec: 0,
      transition_in: 'cut', hook: false, hook_text: '',
    }
    t.splice(i + 1, 0, fresh)
    patch({ timeline: t })
  }

  return (
    <>
      <div className="st-review-bar">
        <div>
          <div className="st-review-topic">{plan.topic || (vi ? 'Kế hoạch truyện' : 'Story plan')}</div>
          <div className="st-muted">
            {plan.characters.length} {vi ? 'nhân vật' : 'characters'} · {plan.visuals.length} {vi ? 'hình' : 'visuals'} ·{' '}
            {plan.timeline.length} {vi ? 'phân đoạn' : 'beats'} · ~{mm}m {ss}s
          </div>
        </div>
        <div className="st-actions">
          <button type="button" className="st-btn" disabled={busy} onClick={onBack}>
            {vi ? '‹ Sửa nguồn' : '‹ Edit source'}
          </button>
          <button type="button" className="st-btn st-btn--primary" disabled={busy} onClick={onRender}>
            {busy ? (vi ? 'Đang gửi…' : 'Submitting…') : (vi ? '🎥 Render' : '🎥 Render')}
          </button>
        </div>
      </div>

      <CharactersPanel vi={vi} plan={plan} artStyle={artStyle} onChange={updateCharacter} />
      <VisualsPanel
        vi={vi} plan={plan} artStyle={artStyle} aspect={aspect} colors={colors}
        previews={previews} setPreview={(id, url) => setPreviews((p) => ({ ...p, [id]: url }))}
        onChange={updateVisual}
      />
      <TimelineEditor
        vi={vi} plan={plan} language={language} colors={colors} previews={previews}
        onChangeBeat={updateBeat} onMove={moveBeat} onDelete={deleteBeat} onAdd={addBeatAfter}
      />
    </>
  )
}
