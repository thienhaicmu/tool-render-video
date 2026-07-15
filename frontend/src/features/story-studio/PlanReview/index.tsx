/**
 * PlanReview — Story v2 phase 2 (F3): review + EDIT the StoryPlan before render.
 *
 * Three panels over the same immutable plan (edits flow up via setPlan):
 *   CharactersPanel — name · canonical_desc · voice · optional character master
 *   VisualsPanel    — per key-visual prompt/negative/characters + SVG preview
 *   TimelineEditor  — the beat list (narration · visual · focus/motion/transition
 *                     · emotion/pose · hook) with reorder / add / delete + live duration
 *
 * Story Mode is SVG-only: previews are composed procedurally server-side (offline, $0,
 * WYSIWYG) via /api/story/visual/svg-preview. A locally-held ``previews`` map
 * (visual_id → image url) is shared so the TimelineEditor can thumbnail each visual.
 */
import { useEffect, useRef, useState } from 'react'
import type { StoryPlanV2, Beat, Visual, CharacterDef } from '../../../api/story'
import { svgPreview } from '../../../api/story'
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

export function PlanReview({ vi, plan, setPlan, busy, artStyle, aspect, language,
  onRender, onBack }: {
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
  const setPreview = (id: string, url: string) => setPreviews((p) => ({ ...p, [id]: url }))

  // On entering Review, compose the procedural SVG for the whole storyboard so the user
  // sees exactly what the render will produce (WYSIWYG, offline $0). One batch call.
  const draftRan = useRef(false)
  const [drafting, setDrafting] = useState(false)
  const [draftMsg, setDraftMsg] = useState('')

  async function draftAll(force = false) {
    if (drafting) return
    const targets = plan.visuals.filter((v) => force || !previews[v.id])
    if (!targets.length) return
    setDrafting(true)
    setDraftMsg(vi ? 'Đang dựng ảnh…' : 'Composing…')
    try {
      const r = await svgPreview({ plan, visual_ids: targets.map((v) => v.id) })
      for (const it of r.items) setPreview(it.visual_id, it.url)
    } catch { /* best-effort — a badge fallback shows where a preview is missing */ }
    setDrafting(false); setDraftMsg('')
  }

  useEffect(() => {
    if (draftRan.current) return
    draftRan.current = true
    void draftAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Library-pick matching visibility (D3): how many characters/settings the AI resolved
  // to a library asset slug (the rest fall back to fuzzy match → procedural art).
  const libChars = plan.characters.filter((c) => (c.asset || '').trim()).length
  const libSettings = plan.settings.filter((s) => (s.asset || '').trim()).length
  const colors = visualColorMap(plan.visuals)
  const liveTotal = plan.timeline.reduce(
    (s, b) => s + beatEstSec(b, language) + Math.max(0, b.pause_after || 0), 0)
  const mm = Math.floor(liveTotal / 60)
  const ss = Math.round(liveTotal % 60)

  const patch = (p: Partial<StoryPlanV2>) => setPlan({ ...plan, ...p })
  const updateCharacter = (id: string, up: Partial<CharacterDef>) =>
    patch({ characters: plan.characters.map((c) => (c.id === id ? { ...c, ...up } : c)) })
  // Per-character voice override → written into render.voices ([engine, voice_id]);
  // preserved at render (apply_voice_cast_v2 keeps a user-set voice). "" voice_id
  // clears the override back to auto-cast.
  const updateVoice = (cid: string, engine: string, voiceId: string) =>
    patch({ render: { ...plan.render, voices: { ...(plan.render?.voices ?? {}), [cid]: [engine, voiceId] } } })
  // A5 — lock a chosen character master into the plan so the render reuses that exact
  // image (skips render-time regeneration). "" clears the lock (back to auto).
  const updateMaster = (cid: string, path: string) => {
    const masters = { ...(plan.render?.masters ?? {}) }
    if (path) masters[cid] = path; else delete masters[cid]
    patch({ render: { ...plan.render, masters } })
  }
  // GĐ3 — a manual library pick assigns the ASSET IDENTITY in one step: the slug on
  // the character (resolver treats it as matched_exact), the file as locked master,
  // and the status chip flips accordingly.
  const updateAssetPick = (cid: string, slug: string, path: string) => {
    const masters = { ...(plan.render?.masters ?? {}) }
    if (path) masters[cid] = path
    const asset_status = { ...(plan.render?.asset_status ?? {}), [cid]: 'matched_exact' }
    patch({
      characters: plan.characters.map((c) => (c.id === cid ? { ...c, asset: slug } : c)),
      render: { ...plan.render, masters, asset_status },
    })
  }
  const updateVisual = (id: string, up: Partial<Visual>) =>
    patch({ visuals: plan.visuals.map((v) => (v.id === id ? { ...v, ...up } : v)) })
  // AL4 — pin a library background into render.visual_assets so the render reuses that
  // exact file (library-first, skips SVG compose). "" clears it (back to procedural).
  const updateVisualAsset = (id: string, path: string) => {
    const va = { ...(plan.render?.visual_assets ?? {}) }
    if (path) va[id] = path; else delete va[id]
    patch({ render: { ...plan.render, visual_assets: va } })
  }
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
      focus: 'center', motion: 'zoom_in', emotion: 'normal', pose: 'stand',
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
            {(libChars > 0 || libSettings > 0) && (
              <span className="st-tag st-tag--dim" style={{ marginLeft: 8 }}
                title={vi ? 'Số nhân vật/cảnh AI khớp sẵn từ kho (còn lại vẽ tự động)'
                          : 'Characters/scenes the AI matched from the library (rest are procedural)'}>
                📚 {vi ? 'kho' : 'lib'} {libChars}/{plan.characters.length} · {libSettings}/{plan.settings.length}
              </span>
            )}
          </div>
        </div>
        <div className="st-actions">
          <span className="st-tag st-tag--dim" title={vi ? 'Ảnh chibi vẽ trong máy — offline, $0' : 'Chibi art rendered locally — offline, $0'}>
            🖍 {vi ? 'Chibi · $0' : 'Chibi · $0'}
          </span>
          <button type="button" className="st-btn" disabled={busy || drafting} onClick={() => void draftAll(true)}>
            {drafting ? draftMsg : (vi ? '↻ Dựng lại ảnh' : '↻ Recompose')}
          </button>
          <button type="button" className="st-btn" disabled={busy} onClick={onBack}>
            {vi ? '‹ Sửa nguồn' : '‹ Edit source'}
          </button>
          <button type="button" className="st-btn st-btn--primary" disabled={busy} onClick={onRender}>
            {busy ? (vi ? 'Đang gửi…' : 'Submitting…') : (vi ? '🎥 Render · $0' : '🎥 Render · $0')}
          </button>
        </div>
      </div>

      <CharactersPanel vi={vi} plan={plan} artStyle={artStyle} language={language}
        onChange={updateCharacter} onVoiceChange={updateVoice} onMasterChange={updateMaster}
        onAssetPick={updateAssetPick} />
      <VisualsPanel
        vi={vi} plan={plan} aspect={aspect} colors={colors}
        previews={previews} setPreview={setPreview}
        onChange={updateVisual} onVisualAsset={updateVisualAsset}
      />
      <TimelineEditor
        vi={vi} plan={plan} language={language} colors={colors} previews={previews}
        onChangeBeat={updateBeat} onMove={moveBeat} onDelete={deleteBeat} onAdd={addBeatAfter}
      />
    </>
  )
}
