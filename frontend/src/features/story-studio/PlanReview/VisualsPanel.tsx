/**
 * VisualsPanel — Story v2 review (F3): edit each key-visual's prompt / negative /
 * characters and PREVIEW it (POST /api/story/visual/svg-preview → procedural SVG image).
 * The preview url is lifted to the parent so the TimelineEditor can thumbnail it.
 * Story Mode is SVG-only — offline, $0. Studio BASE only.
 */
import { useState } from 'react'
import { StudioCard } from '../../../components/studio'
import type { StoryPlanV2, Visual } from '../../../api/story'
import { svgPreview } from '../../../api/story'
import { storyAssetImageUrl } from '../../../api/storyAssets'
import type { Aspect } from '../types'
import { AssetPicker } from './AssetPicker'

export function VisualsPanel({ vi, plan, aspect, colors, previews, setPreview, onChange, onVisualAsset }: {
  vi: boolean
  plan: StoryPlanV2
  aspect: Aspect
  colors: Record<string, string>
  previews: Record<string, string>
  setPreview: (visualId: string, url: string) => void
  onChange: (id: string, up: Partial<Visual>) => void
  onVisualAsset: (visualId: string, path: string) => void
}) {
  if (!plan.visuals.length) return null
  return (
    <StudioCard icon="🖼️" title={vi ? 'Key-visual' : 'Key visuals'} aside={`${plan.visuals.length}`}>
      <div className="st-visual-grid">
        {plan.visuals.map((v) => (
          <VisualCard key={v.id} vi={vi} v={v} plan={plan} aspect={aspect}
            color={colors[v.id]} preview={previews[v.id]} setPreview={setPreview}
            onChange={onChange} onVisualAsset={onVisualAsset} />
        ))}
      </div>
    </StudioCard>
  )
}

function VisualCard({ vi, v, plan, aspect, color, preview, setPreview, onChange, onVisualAsset }: {
  vi: boolean
  v: Visual
  plan: StoryPlanV2
  aspect: Aspect
  color: string
  preview?: string
  setPreview: (visualId: string, url: string) => void
  onChange: (id: string, up: Partial<Visual>) => void
  onVisualAsset: (visualId: string, path: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const [picker, setPicker] = useState(false)
  const settingAsset = (plan.settings.find((s) => s.id === v.setting_id)?.asset || '').trim()

  async function doPreview() {
    if (busy) return
    setBusy(true); setErr(false)
    try {
      const r = await svgPreview({ plan, visual_ids: [v.id] })
      const item = r.items.find((it) => it.visual_id === v.id)
      if (item) setPreview(v.id, item.url); else setErr(true)
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
        {/* Story is SVG-only: the picture is composed procedurally from the visual's
            setting + present characters (the WYSIWYG preview above shows exactly what
            renders). The old image-gen prompt / negative-prompt fields are gone. */}
        {settingAsset && (
          <span className="st-tag st-tag--dim" title={vi ? 'Nền AI khớp sẵn từ kho' : 'AI matched this background from the library'}>
            📚 {settingAsset}
          </span>
        )}
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
          <button type="button" className="st-btn st-btn--sm" disabled={busy} onClick={doPreview}>
            {busy ? (vi ? 'Đang dựng…' : 'Composing…')
              : err ? (vi ? '⚠ Thử lại' : '⚠ Retry')
              : preview ? (vi ? 'Dựng lại' : 'Recompose')
              : (vi ? 'Xem thử' : 'Preview')}
          </button>
          <button type="button" className="st-btn st-btn--sm" onClick={() => setPicker(true)}
            title={vi ? 'Chọn nền có sẵn từ kho (miễn phí, không gọi AI)'
                      : 'Pick an existing background from the library (free, no AI call)'}>
            {vi ? '🗂️ Kho' : '🗂️ Library'}
          </button>
        </div>
      </div>
      {picker && (
        <AssetPicker vi={vi} kind="background"
          onClose={() => setPicker(false)}
          onPick={(a) => {
            setPreview(v.id, storyAssetImageUrl(a.id))
            onVisualAsset(v.id, a.path)         // library-first: render reuses this, skips AI
          }} />
      )}
    </div>
  )
}
