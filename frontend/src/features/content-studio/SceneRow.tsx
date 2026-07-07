/**
 * SceneRow.tsx — one editable scene card in the Review phase (CM-9 split).
 * Narration edit + voice preview + per-scene visual preview/regenerate +
 * per-scene background (Asset Manager). Extracted verbatim from ContentStudio.tsx.
 */
import { useRef, useState } from 'react'
import { previewNarration, previewVisual, pinVisual, type ContentScene } from '../../api/content'
import { BASE_URL } from '../../api/client'
import { sceneAudit } from './shared'
import { EMOTIONS, type VoiceCfg, type VisualCfg } from './types'

export function SceneRow({ vi, scene, index, total, voice, visualCfg, onChange, onRemove, onMove }: {
  vi: boolean; scene: ContentScene; index: number; total: number; voice: VoiceCfg; visualCfg: VisualCfg
  onChange: (patch: Partial<ContentScene>) => void; onRemove: () => void; onMove: (dir: -1 | 1) => void
}) {
  const [previewing, setPreviewing] = useState(false)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [dur, setDur] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const hasText = !!(scene.narration || '').trim()
  const audit = sceneAudit(scene)

  // C1: per-scene visual preview.
  const [vImg, setVImg] = useState<string | null>(null)      // shown image URL
  const [vNote, setVNote] = useState<string | null>(null)    // "fell back to background" / error
  const [vBusy, setVBusy] = useState(false)
  const [vToken, setVToken] = useState<string | null>(null)  // CM-12: preview token (to pin)
  const [pinned, setPinned] = useState(false)                // CM-12: this image pinned to the scene
  const vSeed = useRef(0)
  const hasPrompt = !!(scene.visual_prompt || '').trim()
  const canVisual = visualCfg.provider !== 'local' && hasPrompt

  async function doVisual(regen: boolean) {
    if (!canVisual || vBusy) return
    if (regen) { vSeed.current += 1; setPinned(false) }   // CM-12: a new image is no longer pinned
    setVBusy(true); setVNote(null)
    try {
      const r = await previewVisual({
        prompt: (scene.visual_prompt || '').trim(),
        provider: visualCfg.provider, aspect_ratio: visualCfg.aspectApi,
        seed: vSeed.current, style: visualCfg.style,
        negative_prompt: scene.negative_prompt || '',
        imagen_tier: visualCfg.provider === 'ai_image' ? visualCfg.imagenTier : undefined,
      })
      if (r.kind === 'image' && r.url) {
        setVImg(BASE_URL + r.url + `?t=${Date.now()}`)   // bust cache on regen
        setVToken(r.token || null)
        if (r.provider !== visualCfg.provider) {
          setVNote(vi ? `Đã dùng nguồn "${r.provider}" (nguồn chọn không tạo được).` : `Used "${r.provider}" (chosen source unavailable).`)
        }
      } else {
        setVImg(null); setVToken(null)
        setVNote(vi ? 'Nguồn không tạo được ảnh — khi render sẽ dùng nền màu.' : 'No image produced — the render will use a background colour.')
      }
    } catch (err) {
      setVNote(err instanceof Error ? err.message : String(err))
    } finally {
      setVBusy(false)
    }
  }

  // CM-12: pin the previewed image as a durable asset → the render uses THIS
  // exact image for the scene (visual_source='image' + visual_path), instead of
  // regenerating. Enables Ken Burns so a still image gets subtle motion.
  async function doPin() {
    if (!vToken || vBusy || pinned) return
    setVBusy(true)
    try {
      const r = await pinVisual(vToken)
      onChange({ visual_source: 'image', visual_path: r.path, ken_burns: true })
      setPinned(true)
      setVNote(vi ? '📌 Đã ghim — cảnh sẽ dùng đúng ảnh này khi render.' : '📌 Pinned — the scene will use this exact image.')
    } catch (err) {
      setVNote(err instanceof Error ? err.message : String(err))
    } finally {
      setVBusy(false)
    }
  }

  async function doPreview() {
    if (!hasText || previewing) return
    setPreviewErr(null); setPreviewing(true)
    try {
      const r = await previewNarration({
        text: (scene.narration || '').trim(),
        voice_language: voice.lang, voice_gender: voice.gender,
        tts_engine: voice.engine, reading_speed: scene.reading_speed ?? 1,
      })
      setDur(r.duration_sec)
      if (audioRef.current) audioRef.current.pause()
      const a = new Audio(BASE_URL + r.url)
      audioRef.current = a
      void a.play().catch(() => {})
    } catch (err) {
      setPreviewErr(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section className="cs-card cs-card--flush">
      <div className="cs-card-hd">
        <input className="cs-input cs-scene-title-input" value={scene.scene_title || ''} placeholder={`${vi ? 'Cảnh' : 'Scene'} ${index + 1}`}
          onChange={(e) => onChange({ scene_title: e.target.value })} />
        {audit.flag === 'overloaded' && (
          <span className="cs-audit-badge is-over" title={vi ? 'Lời kể dài hơn thời lượng — TTS sẽ bị hụt/tràn. Rút gọn hoặc tăng thời lượng.' : 'Narration too long for the duration — TTS will rush/overflow. Shorten it or raise the duration.'}>
            {vi ? '⚠ Quá tải' : '⚠ Overloaded'}
          </span>
        )}
        {audit.flag === 'sparse' && (
          <span className="cs-audit-badge is-sparse" title={vi ? 'Lời kể ngắn so với thời lượng — sẽ có khoảng lặng. Thêm lời hoặc giảm thời lượng.' : 'Narration short for the duration — expect silence. Add narration or lower the duration.'}>
            {vi ? 'Thưa' : 'Sparse'}
          </span>
        )}
        <div className="cs-row" style={{ gap: 4 }}>
          <button className={`cs-icon-btn${hasText ? ' is-accent' : ''}`} title={vi ? 'Nghe thử giọng' : 'Preview voice'}
            disabled={!hasText || previewing} onClick={doPreview}>{previewing ? '…' : '🔊'}</button>
          {canVisual && (
            <button className="cs-icon-btn is-accent"
              title={(visualCfg.provider === 'ai_image' || visualCfg.provider === 'ai_video')
                ? (vi ? 'Xem thử ảnh — TỐN PHÍ mỗi lần (Imagen/Veo)' : 'Preview image — PAID per call (Imagen/Veo)')
                : (vi ? 'Xem thử ảnh (miễn phí)' : 'Preview image (free)')}
              disabled={vBusy} onClick={() => doVisual(false)}>{vBusy ? '…' : '🖼️'}</button>
          )}
          <button className="cs-icon-btn" title="Up" disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
          <button className="cs-icon-btn" title="Down" disabled={index === total - 1} onClick={() => onMove(1)}>↓</button>
          <button className="cs-icon-btn is-danger" title="Delete" onClick={onRemove}>✕</button>
        </div>
      </div>
      <textarea className="cs-textarea cs-textarea--sm" value={scene.narration}
        placeholder={vi ? 'Lời kể…' : 'Narration…'} onChange={(e) => onChange({ narration: e.target.value })} />
      <div className="cs-row">
        <label className="cs-mini-label">{vi ? 'Cảm xúc' : 'Emotion'}
          <select className="cs-input-sm" value={scene.emotion || 'normal'} onChange={(e) => onChange({ emotion: e.target.value })}>
            {EMOTIONS.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
          </select>
        </label>
        <label className="cs-mini-label">{vi ? 'Tốc độ' : 'Speed'}
          <input type="number" step={0.05} min={0.5} max={2} className="cs-input-sm" value={scene.reading_speed ?? 1}
            onChange={(e) => onChange({ reading_speed: Number(e.target.value) || 1 })} />
        </label>
        <label className="cs-mini-label">{vi ? 'Thời lượng (s)' : 'Dur (s)'}
          <input type="number" step={0.5} min={0} className="cs-input-sm" value={scene.est_duration_sec ?? 0}
            onChange={(e) => onChange({ est_duration_sec: Number(e.target.value) || 0 })} />
        </label>
        <label className="cs-mini-label" style={{ flex: 1, minWidth: 200 }}>{vi ? 'Visual prompt' : 'Visual prompt'}
          <input className="cs-input-sm" value={scene.visual_prompt || ''} onChange={(e) => onChange({ visual_prompt: e.target.value })}
            placeholder={vi ? 'Mô tả hình ảnh cho scene này…' : 'Image/video prompt for this scene…'} />
        </label>
      </div>
      {/* C1: per-scene visual preview (image + regenerate). */}
      {(vImg || vNote) && (
        <div style={{ marginTop: 8 }}>
          {vImg && <img src={vImg} alt="" style={{ maxWidth: 160, maxHeight: 280, borderRadius: 8, display: 'block' }} />}
          <div className="cs-row" style={{ gap: 8, alignItems: 'center', marginTop: 6 }}>
            {vImg && (
              <button className="cs-icon-btn" title={vi ? 'Tạo lại ảnh' : 'Regenerate image'}
                disabled={vBusy} onClick={() => doVisual(true)}>{vBusy ? '…' : '🔄'}</button>
            )}
            {vImg && vToken && (
              <button className={`cs-icon-btn${pinned ? '' : ' is-accent'}`}
                title={pinned ? (vi ? 'Đã ghim ảnh cho cảnh' : 'Pinned to the scene')
                              : (vi ? 'Dùng ảnh này cho cảnh (ghim)' : 'Use this image for the scene (pin)')}
                disabled={vBusy || pinned} onClick={doPin}>{pinned ? '📌✓' : '📌'}</button>
            )}
            {vNote && <span className="cs-hint" style={{ margin: 0, color: vImg ? undefined : 'var(--warn, #d6a200)' }}>{vNote}</span>}
          </div>
        </div>
      )}
      {/* CS-E: per-scene background (Asset Manager). "" = dùng nền chung của project. */}
      <div className="cs-row cs-row--top" style={{ alignItems: 'flex-end' }}>
        <label className="cs-mini-label">{vi ? 'Nền riêng' : 'Scene background'}
          <select className="cs-input-sm" value={scene.visual_source || ''}
            onChange={(e) => onChange({ visual_source: e.target.value as ContentScene['visual_source'] })}>
            <option value="">{vi ? 'Nền chung' : 'Project default'}</option>
            <option value="color">{vi ? 'Màu' : 'Color'}</option>
            <option value="image">{vi ? 'Ảnh' : 'Image'}</option>
            <option value="video">Video</option>
          </select>
        </label>
        {scene.visual_source === 'color' && (
          <label className="cs-mini-label">{vi ? 'Màu' : 'Color'}
            <input type="color" className="cs-color-swatch" value={scene.visual_path || '#101820'} onChange={(e) => onChange({ visual_path: e.target.value })} />
          </label>
        )}
        {(scene.visual_source === 'image' || scene.visual_source === 'video') && (
          <label className="cs-mini-label" style={{ flex: 1, minWidth: 200 }}>{vi ? 'Đường dẫn file' : 'File path'}
            <input className="cs-input-sm" value={scene.visual_path || ''} onChange={(e) => onChange({ visual_path: e.target.value })}
              placeholder={vi ? 'Đường dẫn ảnh/video trên máy…' : 'Local image/video path…'} />
          </label>
        )}
        {scene.visual_source === 'image' && (
          <label className="cs-mini-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={!!scene.ken_burns} onChange={(e) => onChange({ ken_burns: e.target.checked })} />
            Ken Burns
          </label>
        )}
      </div>
      {(dur != null || previewErr) && (
        <div className="cs-hint" style={{ color: previewErr ? 'var(--fail)' : undefined }}>
          {previewErr ? previewErr : `${vi ? 'Giọng ~' : 'Voice ~'}${(dur ?? 0).toFixed(1)}s`}
        </div>
      )}
    </section>
  )
}
