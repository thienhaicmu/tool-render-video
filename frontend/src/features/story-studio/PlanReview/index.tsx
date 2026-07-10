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
import { useEffect, useRef, useState } from 'react'
import type { StoryPlanV2, Beat, Visual, CharacterDef } from '../../../api/story'
import { previewVisual } from '../../../api/story'
import type { Aspect, ImageProvider, StoryLang } from '../types'
import { PREMIUM_IMG_COST_USD } from '../types'
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

export function PlanReview({ vi, plan, setPlan, busy, artStyle, aspect, language,
  imageProvider, onImageProvider, onRender, onBack }: {
  vi: boolean
  plan: StoryPlanV2
  setPlan: (p: StoryPlanV2) => void
  estTotal: number
  busy: boolean
  artStyle: string
  aspect: Aspect
  language: StoryLang
  imageProvider: ImageProvider
  onImageProvider: (p: ImageProvider) => void
  onRender: () => void
  onBack: () => void
}) {
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const setPreview = (id: string, url: string) => setPreviews((p) => ({ ...p, [id]: url }))

  // Phase 2 (draft/final split): on entering Review, auto-generate a FREE draft image
  // for the whole storyboard so the user sees it BEFORE paying for the premium final.
  // Sequential + best-effort (gentle on the free service; one bad image never blocks).
  const draftRan = useRef(false)
  const [drafting, setDrafting] = useState(false)
  const [draftMsg, setDraftMsg] = useState('')

  async function draftAll(force = false) {
    if (drafting) return
    const targets = plan.visuals.filter((v) => v.prompt.trim() && (force || !previews[v.id]))
    if (!targets.length) return
    setDrafting(true)
    let done = 0
    for (const v of targets) {
      setDraftMsg(vi ? `Đang tạo nháp ${done + 1}/${targets.length}…` : `Drafting ${done + 1}/${targets.length}…`)
      try {
        const r = await previewVisual({
          prompt: v.prompt, negative_prompt: v.negative_prompt,
          art_style: artStyle, aspect_ratio: aspect, tier: v.tier,
          provider: 'pollinations',   // draft = FREE regardless of the final choice
        })
        setPreview(v.id, r.url)
      } catch { /* best-effort per visual */ }
      done++
    }
    setDrafting(false); setDraftMsg('')
  }

  useEffect(() => {
    if (draftRan.current) return
    draftRan.current = true
    void draftAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const premiumCost = (plan.visuals.length * PREMIUM_IMG_COST_USD).toFixed(2)
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
          {/* Phase 2 — pick what the FINAL render uses (draft above is always free). */}
          <div className="st-provider" role="group" aria-label={vi ? 'Chất lượng ảnh' : 'Image quality'}>
            <button type="button" className={`st-provider-opt${imageProvider === 'pollinations' ? ' is-on' : ''}`}
              disabled={busy} onClick={() => onImageProvider('pollinations')}
              title={vi ? 'Ảnh miễn phí (Flux) — $0' : 'Free images (Flux) — $0'}>
              {vi ? 'Free' : 'Free'} · $0
            </button>
            <button type="button" className={`st-provider-opt${imageProvider === 'gpt_image' ? ' is-on' : ''}`}
              disabled={busy} onClick={() => onImageProvider('gpt_image')}
              title={vi ? 'Ảnh cao cấp (gpt-image-1) — nhân vật nhất quán' : 'Premium (gpt-image-1) — consistent characters'}>
              {vi ? 'Premium' : 'Premium'} · ~${premiumCost}
            </button>
          </div>
          <button type="button" className="st-btn" disabled={busy || drafting} onClick={() => void draftAll(true)}>
            {drafting ? draftMsg : (vi ? '↻ Nháp lại' : '↻ Re-draft')}
          </button>
          <button type="button" className="st-btn" disabled={busy} onClick={onBack}>
            {vi ? '‹ Sửa nguồn' : '‹ Edit source'}
          </button>
          <button type="button" className="st-btn st-btn--primary" disabled={busy} onClick={onRender}>
            {busy ? (vi ? 'Đang gửi…' : 'Submitting…')
              : imageProvider === 'gpt_image'
                ? (vi ? `🎥 Render · ~$${premiumCost}` : `🎥 Render · ~$${premiumCost}`)
                : (vi ? '🎥 Render · Free' : '🎥 Render · Free')}
          </button>
        </div>
      </div>

      {imageProvider === 'gpt_image' && plan.visuals.length >= 8 && (
        <div className="st-cost-hint">
          {vi
            ? `💡 ${plan.visuals.length} ảnh Premium ≈ $${premiumCost}. Bản nháp trên đã miễn phí — chuyển "Free" nếu muốn render $0.`
            : `💡 ${plan.visuals.length} premium images ≈ $${premiumCost}. The drafts above are free — switch to "Free" to render at $0.`}
        </div>
      )}

      <CharactersPanel vi={vi} plan={plan} artStyle={artStyle} onChange={updateCharacter} />
      <VisualsPanel
        vi={vi} plan={plan} artStyle={artStyle} aspect={aspect} colors={colors}
        previews={previews} setPreview={setPreview}
        onChange={updateVisual}
      />
      <TimelineEditor
        vi={vi} plan={plan} language={language} colors={colors} previews={previews}
        onChangeBeat={updateBeat} onMove={moveBeat} onDelete={deleteBeat} onAdd={addBeatAfter}
      />
    </>
  )
}
