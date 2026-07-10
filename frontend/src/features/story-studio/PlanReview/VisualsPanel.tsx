/**
 * VisualsPanel — Story v2 review (F3): edit each key-visual's prompt / negative /
 * characters / tier and PREVIEW it (POST /api/story/visual/preview → one image).
 * The preview url is lifted to the parent so the TimelineEditor can thumbnail it.
 * Studio BASE only.
 */
import { useState } from 'react'
import { StudioCard, StudioField } from '../../../components/studio'
import type { StoryPlanV2, Visual } from '../../../api/story'
import { previewVisual } from '../../../api/story'
import { TIER, type Aspect } from '../types'

export function VisualsPanel({ vi, plan, artStyle, aspect, colors, previews, setPreview, onChange }: {
  vi: boolean
  plan: StoryPlanV2
  artStyle: string
  aspect: Aspect
  colors: Record<string, string>
  previews: Record<string, string>
  setPreview: (visualId: string, url: string) => void
  onChange: (id: string, up: Partial<Visual>) => void
}) {
  if (!plan.visuals.length) return null
  return (
    <StudioCard icon="🖼️" title={vi ? 'Key-visual' : 'Key visuals'} aside={`${plan.visuals.length}`}>
      <div className="st-visual-grid">
        {plan.visuals.map((v) => (
          <VisualCard key={v.id} vi={vi} v={v} plan={plan} artStyle={artStyle} aspect={aspect}
            color={colors[v.id]} preview={previews[v.id]} setPreview={setPreview} onChange={onChange} />
        ))}
      </div>
    </StudioCard>
  )
}

function VisualCard({ vi, v, plan, artStyle, aspect, color, preview, setPreview, onChange }: {
  vi: boolean
  v: Visual
  plan: StoryPlanV2
  artStyle: string
  aspect: Aspect
  color: string
  preview?: string
  setPreview: (visualId: string, url: string) => void
  onChange: (id: string, up: Partial<Visual>) => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)

  async function doPreview() {
    if (busy || !v.prompt.trim()) return
    setBusy(true); setErr(false)
    try {
      const r = await previewVisual({
        prompt: v.prompt, negative_prompt: v.negative_prompt,
        art_style: artStyle, aspect_ratio: aspect, tier: v.tier,
      })
      setPreview(v.id, r.url)
    } catch { setErr(true) } finally { setBusy(false) }
  }

  function toggleChar(cid: string) {
    const has = v.character_ids.includes(cid)
    onChange(v.id, { character_ids: has ? v.character_ids.filter((x) => x !== cid) : [...v.character_ids, cid] })
  }

  return (
    <div className="st-visual">
      <div className={`st-visual-thumb st-visual-thumb--${aspect.replace(':', '-')}`}
        style={{ borderColor: color }}>
        {preview
          ? <img src={preview} alt={v.id} />
          : <span className="st-visual-badge" style={{ background: color }}>{v.id}</span>}
        {busy && <span className="st-visual-spin" aria-hidden />}
      </div>
      <div className="st-visual-body">
        <StudioField label={vi ? 'Mô tả hình' : 'Prompt'}>
          <textarea className="st-textarea st-textarea--sm" rows={3} value={v.prompt}
            onChange={(e) => onChange(v.id, { prompt: e.target.value })} />
        </StudioField>
        <StudioField label={vi ? 'Tránh (negative)' : 'Negative'}>
          <input className="st-input" value={v.negative_prompt}
            onChange={(e) => onChange(v.id, { negative_prompt: e.target.value })} />
        </StudioField>
        {plan.characters.length > 0 && (
          <div className="st-chip-row">
            {plan.characters.map((c) => (
              <button key={c.id} type="button"
                className={`st-chip${v.character_ids.includes(c.id) ? ' is-on' : ''}`}
                onClick={() => toggleChar(c.id)}>{c.name || c.id}</button>
            ))}
          </div>
        )}
        <div className="st-visual-foot">
          <select className="st-select st-select--sm" value={v.tier}
            onChange={(e) => onChange(v.id, { tier: e.target.value })}>
            {TIER.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button type="button" className="st-btn st-btn--sm" disabled={busy || !v.prompt.trim()} onClick={doPreview}>
            {busy ? (vi ? 'Đang tạo…' : 'Rendering…')
              : err ? (vi ? '⚠ Thử lại' : '⚠ Retry')
              : preview ? (vi ? 'Tạo lại' : 'Regenerate')
              : (vi ? 'Xem thử' : 'Preview')}
          </button>
        </div>
      </div>
    </div>
  )
}
